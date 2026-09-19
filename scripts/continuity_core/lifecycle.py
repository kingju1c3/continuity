"""Cooperative single-writer session handoff. No trust changes or private APIs."""
import json
import os
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from .store import canonical, digest, now, check_text

CHECKPOINT_KEYS = {'goal','summary','constraints','decisions','accomplished','pending','blockers','next_actions','relevant_files','record_ids'}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(canonical(data) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists(): temp.unlink()


def artifact(project, relative):
    p = project / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Artifact must be relative to this worktree')
    if any((project.joinpath(*Path(relative).parts[:i])).is_symlink() for i in range(1,len(Path(relative).parts)+1)):
        raise ValueError('Artifact symlinks are not accepted')
    if not p.is_file() or not p.resolve().is_relative_to(project):
        raise ValueError('Required artifact missing: ' + relative)
    return {'path': relative, 'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}


def git_state(project):
    def run(*args):
        r = subprocess.run(['git','-C',str(project),*args],capture_output=True,text=True,timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    return {'head':run('rev-parse','HEAD'),'branch':run('branch','--show-current'),'status':run('status','--porcelain')}


def run_launcher(plan):
    return subprocess.run(plan,capture_output=True,text=True,timeout=8,check=False)


class Lifecycle:
    def __init__(self, store, scope, project):
        self.directory = Path(store).expanduser().resolve() / 'sessions'
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.scope = scope
        self.project = Path(project).expanduser().resolve()
        if not self.project.is_dir(): raise ValueError('Project does not exist')
        self.key = digest(canonical([scope,str(self.project)]))
        self.db = sqlite3.connect(self.directory/'lifecycle.sqlite3',timeout=2)
        self.db.execute('PRAGMA busy_timeout=2000')
        self.db.execute('CREATE TABLE IF NOT EXISTS chains (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.db.commit()
        os.chmod(self.directory/'lifecycle.sqlite3',0o600)

    def close(self): self.db.close()

    def read(self):
        row=self.db.execute('SELECT data FROM chains WHERE id=?',(self.key,)).fetchone()
        if not row: raise ValueError('Configure lifecycle automation for this exact project first')
        return json.loads(row[0])

    def change(self, operation):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            state=self.read()
            result=operation(state)
            state['revision']+=1
            self.db.execute('UPDATE chains SET data=? WHERE id=?',(canonical(state),self.key))
            self.db.commit()
            return result
        except BaseException:
            self.db.rollback()
            raise

    def configure(self, host, launcher, auto=False, max_turns=8, max_launches=5):
        if host not in {'claude','codex'} or launcher not in {'manual','tmux','terminal'}:
            raise ValueError('Unsupported host or launcher')
        if auto and launcher=='manual': raise ValueError('Automatic opening needs tmux or macOS Terminal')
        if not 1<=max_turns<=100 or not 1<=max_launches<=20: raise ValueError('Invalid rotation bounds')
        state={'schema':1,'revision':1,'scope':self.scope,'project':str(self.project),'host':host,'launcher':launcher,'auto':auto,
               'armed':True,'owner':None,'owner_ended':False,'phase':'owned','turn':0,'requested_turn':-1,'packet_turn':-1,
               'packet':None,'pending':None,'attempts':0,'max_launches':max_launches,'max_turns':max_turns,'generation':0,
               'events_seen':{},'last_issue':None}
        with self.db:
            self.db.execute('INSERT INTO chains VALUES(?,?)',(self.key,canonical(state)))
        return state

    def packet(self):
        state=self.read()
        if not state['packet']: raise ValueError('No complete lifecycle checkpoint is available')
        data=json.loads(Path(state['packet']['path']).read_text())
        if digest(canonical(data['payload']))!=data['sha256'] or data['sha256']!=state['packet']['sha256']:
            raise ValueError('Checkpoint digest mismatch')
        if data['payload']['project']!=str(self.project) or data['payload']['scope']!=self.scope:
            raise ValueError('Checkpoint worktree/scope mismatch')
        return data

    def verify_packet(self):
        envelope=self.packet()
        p=envelope['payload']
        for a in p['artifacts']:
            if artifact(self.project,a['path'])!=a: raise ValueError('Required artifact changed: '+a['path'])
        if git_state(self.project)['head']!=p['git']['head']: raise ValueError('Git HEAD changed since the checkpoint')
        return envelope

    def save_packet(self, session, data):
        if not isinstance(data,dict): raise ValueError('Handoff must be an object')
        allowed={'checkpoint','permissions','failed_approaches','open_questions','omissions','required_artifacts','writers_quiesced','mission_complete'}
        if set(data)!=allowed: raise ValueError('Handoff must contain exactly the fields in handoff.example.json')
        cp=data.get('checkpoint')
        if not isinstance(cp,dict) or set(cp)-CHECKPOINT_KEYS: raise ValueError('Invalid checkpoint shape')
        for k in ['goal','summary']: check_text(cp.get(k))
        if not isinstance(cp.get('next_actions'),list) or not cp['next_actions'] or not all(isinstance(v,str) and v.strip() for v in cp['next_actions']):
            raise ValueError('Concrete next actions are required')
        for key in CHECKPOINT_KEYS-{'goal','summary'}:
            if key in cp and (not isinstance(cp[key],list) or not all(isinstance(v,str) for v in cp[key])): raise ValueError('Invalid checkpoint list: '+key)
        for k in ['permissions','failed_approaches','open_questions','omissions','required_artifacts']:
            if not isinstance(data.get(k),list) or not all(isinstance(v,str) for v in data[k]): raise ValueError('Missing list: '+k)
        if data.get('writers_quiesced') is not True: raise ValueError('Stop in-flight writers before freezing a handoff')
        if not isinstance(data.get('mission_complete'),bool): raise ValueError('mission_complete must be explicit')
        check_text(canonical(data))
        artifacts=[artifact(self.project,p) for p in data['required_artifacts']]
        if len({a['path'] for a in artifacts})!=len(artifacts): raise ValueError('Duplicate required artifact')
        payload={'schema':1,'scope':self.scope,'project':str(self.project),'source_session':session,'created':now(),
                 **data,'artifacts':artifacts,'git':git_state(self.project),'quality':'degraded' if data['omissions'] else 'complete-declared'}
        envelope={'payload':payload,'sha256':digest(canonical(payload))}
        path=self.directory/self.key/'checkpoints'/(envelope['sha256']+'.json')
        def save(s):
            if s['owner']!=session or s['phase']!='owned' or not s['armed']: raise ValueError('Only the active owner can prepare a checkpoint')
            atomic_json(path,envelope)
            if json.loads(path.read_text())!=envelope: raise ValueError('Checkpoint readback failed')
            s['packet']={'path':str(path),'sha256':envelope['sha256']}
            s['packet_turn']=s['turn']
            if data['mission_complete']: s['armed']=False
            return s['packet']
        return self.change(save)

    def accept(self, session, checkpoint_digest, first_action, artifacts_read):
        envelope=self.verify_packet()
        p=envelope['payload']
        if checkpoint_digest!=envelope['sha256'] or first_action!=p['checkpoint']['next_actions'][0]: raise ValueError('Checkpoint or first-action acknowledgment mismatch')
        expected=[a['path'] for a in p['artifacts']]
        if sorted(artifacts_read)!=sorted(expected): raise ValueError('Acknowledge every required artifact exactly once')
        def accept(s):
            pending=s['pending']
            if not pending or pending.get('candidate')!=session or pending['digest']!=checkpoint_digest: raise ValueError('No matching observed candidate')
            if s.get('owner_permission_mode') is None or pending.get('permission_mode')!=s['owner_permission_mode']:
                raise ValueError('Candidate permission mode is unknown or differs; review the host before takeover')
            old=s['owner']
            s.update(owner=session,owner_ended=False,phase='owned',pending=None,turn=0,packet_turn=-1,requested_turn=-1,generation=s['generation']+1)
            s['last_transfer']={'from':old,'to':session,'digest':checkpoint_digest,'first_action':first_action,'artifacts_read':artifacts_read,'at':now()}
            return {'owner':session,'predecessor_must_stop':True,'generation':s['generation']}
        return self.change(accept)

    def launch_plan(self, state, nonce):
        executable=shutil.which('claude' if state['host']=='claude' else 'codex')
        if not executable: raise ValueError('Native CLI is not installed: '+state['host'])
        prompt='Use Continuity. Read the complete checkpoint at '+state['packet']['path']+'. You are a read-only successor until the startup instructions verify and accept this exact handoff. Then continue its authorized mission.'
        command=['env','CONTINUITY_HANDOFF_NONCE='+nonce,executable,prompt]
        shell_command='cd '+shlex.quote(str(self.project))+' && exec '+shlex.join(command)
        if state['launcher']=='tmux':
            if not shutil.which('tmux') or not os.environ.get('TMUX'): raise ValueError('tmux launcher needs an active tmux session')
            return ['tmux','new-window','-d','-n','continuity-'+nonce[:8],shell_command]
        if state['launcher']=='terminal':
            if sys.platform!='darwin' or not shutil.which('osascript'): raise ValueError('Terminal launcher requires macOS')
            # JSON string quoting is also valid for the escaped AppleScript string here.
            script='tell application "Terminal"\nactivate\ndo script '+json.dumps(shell_command)+'\nend tell'
            return ['osascript','-e',script]
        return None

    def rotate(self, session, execute=False):
        self.verify_packet()
        s=self.read()
        if s['owner']!=session or s['phase']!='owned' or not s['armed']: raise ValueError('Session is not the active armed owner')
        if s['packet_turn']!=s['turn']: raise ValueError('Checkpoint is stale for this turn')
        if s['attempts']>=s['max_launches']: raise ValueError('Persistent launch cap reached')
        nonce=secrets.token_hex(24)
        plan=self.launch_plan(s,nonce)
        if not execute: return {'command':plan,'launches_remaining':s['max_launches']-s['attempts'],'published':False}
        if plan is None: raise ValueError('Manual launcher: use the complete checkpoint in a new session; no process was opened')
        def reserve(state):
            if state['revision']!=s['revision']: raise ValueError('Concurrent lifecycle change; inspect before retry')
            state['attempts']+=1
            state['phase']='reserved'
            state['pending']={'nonce':nonce,'digest':state['packet']['sha256'],'candidate':None,'outcome':'pending','at':now()}
        self.change(reserve)
        try:
            result=run_launcher(plan)
            outcome='launch-requested' if result.returncode==0 else 'ambiguous'
            detail='Native launcher returned '+str(result.returncode)
        except (OSError,subprocess.TimeoutExpired) as e:
            outcome='ambiguous'
            detail=type(e).__name__
        def record(state):
            if state['pending'] and state['pending']['nonce']==nonce:
                state['pending']['outcome']=outcome
                state['last_issue']=None if outcome=='launch-requested' else detail+'; inspect existing windows, never blindly relaunch'
        self.change(record)
        return {'outcome':outcome,'ready':False,'nonce':nonce,'predecessor_frozen':True}

    def record_context(self, session, measurement):
        required={'session_id','used_tokens','boundary_tokens','next_turn_bound','handoff_reserve','observed_at','source'}
        if not isinstance(measurement,dict) or set(measurement)!=required or measurement['session_id']!=session:
            raise ValueError('Exact-session context measurement required')
        for key in ['used_tokens','boundary_tokens','next_turn_bound','handoff_reserve']:
            if type(measurement[key]) is not int or measurement[key] < (0 if key=='used_tokens' else 1):
                raise ValueError('Invalid context measurement')
        if not isinstance(measurement['observed_at'],(int,float)) or not 0 <= time.time()-measurement['observed_at'] <= 60:
            raise ValueError('Context telemetry must be fresh, not future-dated')
        check_text(measurement['source'])
        def record(s):
            if s['owner']!=session: raise ValueError('Owner mismatch')
            s['context']=measurement
            return {'recorded':True,'source':measurement['source']}
        return self.change(record)

    def control(self, session, action):
        def change(s):
            if s['owner']!=session: raise ValueError('Owner mismatch')
            if action=='disarm': s['armed']=False
            elif action=='cancel':
                if s['pending'] and s['pending'].get('candidate'): raise ValueError('Observed candidate exists; stop it and use explicit recovery')
                # No silent rollback of ambiguous launches.
                raise ValueError('Automatic cancellation is unavailable; inspect the host and use recover with explicit stopped-session evidence')
            return {'armed':s['armed'],'phase':s['phase']}
        return self.change(change)

    def recover(self, session, reason, all_other_sessions_stopped=False):
        if not all_other_sessions_stopped or not reason.strip(): raise ValueError('Explicit stopped-session attestation and reason required')
        self.verify_packet()
        def recover(s):
            s.update(owner=session,owner_ended=False,phase='owned',pending=None,turn=0,packet_turn=-1,requested_turn=-1)
            s['last_recovery']={'at':now(),'reason':reason,'attested_all_other_sessions_stopped':True}
            return {'owner':session,'attempts':s['attempts'],'armed':s['armed']}
        return self.change(recover)
