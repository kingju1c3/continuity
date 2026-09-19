import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from continuity_core.lifecycle import Lifecycle, atomic_json
spec=importlib.util.spec_from_file_location('session_bridge',ROOT/'scripts/continuity_session.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.project=self.root/'project';self.project.mkdir()
        (self.project/'work.py').write_text('print("fixture")\n')
        self.life=Lifecycle(self.root/'vault','project:fixture',self.project)
        self.life.configure('codex','tmux',True,max_turns=2,max_launches=2)
        self.args=argparse.Namespace(store=str(self.root/'vault'),scope='project:fixture',project=str(self.project),host='codex',execute=True)
        self.event('SessionStart')
        self.data=json.loads((ROOT/'assets/handoff.example.json').read_text())
        self.data['checkpoint']['goal']='Finish offline cache'
        self.data['checkpoint']['next_actions']=['Run the cache validation']
        self.data['required_artifacts']=['work.py']

    def tearDown(self):
        self.life.close();self.tmp.cleanup()

    def event(self,name,sid='owner',**kw):
        return bridge.hook(self.life,self.args,{'hook_event_name':name,'session_id':sid,'cwd':str(self.project),'permission_mode':'default',**kw})

    def freeze(self): return self.life.save_packet('owner',self.data)

    def reserve(self):
        self.freeze()
        with patch.object(self.life,'launch_plan',return_value=['fake-launcher']),patch('continuity_core.lifecycle.run_launcher',return_value=subprocess.CompletedProcess([],0,'','')):
            result=self.life.rotate('owner',True)
        self.assertEqual(result['outcome'],'launch-requested')
        return result

    def candidate(self):
        result=self.reserve()
        with patch.dict(os.environ,{'CONTINUITY_HANDOFF_NONCE':result['nonce']}):
            self.event('SessionStart','successor')
        return self.life.packet()['sha256']

    def test_checkpoint_readback_and_scope_binding(self):
        self.freeze()
        self.assertEqual(self.life.verify_packet()['payload']['scope'],'project:fixture')
        other=Lifecycle(self.root/'vault','project:other',self.project)
        try:
            with self.assertRaises(ValueError): other.read()
        finally: other.close()

    def test_reject_missing_or_symlinked_artifact(self):
        self.data['required_artifacts']=['missing.py']
        with self.assertRaises(ValueError): self.freeze()
        (self.project/'link').symlink_to(self.project/'work.py')
        self.data['required_artifacts']=['link']
        with self.assertRaises(ValueError): self.freeze()

    def test_failing_save_preserves_previous_checkpoint(self):
        first=self.freeze()
        self.data['writers_quiesced']=False
        with self.assertRaises(ValueError): self.freeze()
        self.assertEqual(self.life.read()['packet'],first)

    def test_changed_source_blocks_launch_and_accept(self):
        self.freeze();(self.project/'work.py').write_text('changed')
        with self.assertRaises(ValueError): self.life.rotate('owner',True)
        self.assertEqual(self.life.read()['attempts'],0)

    def test_checkpoint_tamper(self):
        packet=self.freeze();p=Path(packet['path']);data=json.loads(p.read_text())
        data['payload']['checkpoint']['goal']='different'
        p.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.life.verify_packet()

    def test_old_owner_frozen_and_successor_requires_readback(self):
        digest=self.candidate()
        denial=self.event('PreToolUse',tool_name='Bash',tool_input={'command':'echo write'})
        self.assertEqual(denial['hookSpecificOutput']['permissionDecision'],'deny')
        with self.assertRaises(ValueError): self.life.accept('successor',digest,'wrong',['work.py'])
        with self.assertRaises(ValueError): self.life.accept('successor',digest,'Run the cache validation',[])
        accepted=self.life.accept('successor',digest,'Run the cache validation',['work.py'])
        self.assertEqual(accepted['owner'],'successor')
        self.assertEqual(self.life.read()['attempts'],1)
        self.assertEqual(self.event('PreToolUse','successor',tool_name='Bash',tool_input={'command':'echo write'}),{})
        self.assertEqual(self.event('PreToolUse',tool_name='Bash',tool_input={'command':'echo write'})['hookSpecificOutput']['permissionDecision'],'deny')

    def test_wrong_candidate_nonce_and_permission_mode(self):
        result=self.reserve()
        self.event('SessionStart','intruder')
        self.assertIsNone(self.life.read()['pending']['candidate'])
        with patch.dict(os.environ,{'CONTINUITY_HANDOFF_NONCE':result['nonce']}):
            self.event('SessionStart','successor',permission_mode='bypassPermissions')
        with self.assertRaises(ValueError): self.life.accept('successor',self.life.packet()['sha256'],'Run the cache validation',['work.py'])

    def test_ambiguous_launch_never_retries(self):
        self.freeze()
        with patch.object(self.life,'launch_plan',return_value=['fake-launcher']),patch('continuity_core.lifecycle.run_launcher',side_effect=subprocess.TimeoutExpired('fake',8)):
            r=self.life.rotate('owner',True)
        self.assertEqual(r['outcome'],'ambiguous')
        with self.assertRaises(ValueError): self.life.rotate('owner',True)
        self.assertEqual(self.life.read()['attempts'],1)

    def test_cap_survives_recovery(self):
        self.reserve()
        self.life.recover('owner','Synthetic failed launch checked and other sessions stopped',True)
        self.reserve()
        self.life.recover('owner','Synthetic second launch stopped',True)
        self.freeze()
        with self.assertRaises(ValueError): self.life.rotate('owner',True)

    def test_stop_requests_one_checkpoint_then_rotates(self):
        self.event('UserPromptSubmit');self.event('UserPromptSubmit')
        first=self.event('Stop')
        self.assertEqual(first['decision'],'block')
        self.assertEqual(self.event('Stop',stop_hook_active=True),{})
        self.freeze()
        with patch.object(self.life,'launch_plan',return_value=['fake']),patch('continuity_core.lifecycle.run_launcher',return_value=subprocess.CompletedProcess([],0,'','')):
            second=self.event('Stop',stop_hook_active=True)
        self.assertFalse(second['continue'])
        self.assertEqual(self.life.read()['attempts'],1)

    def test_mission_complete_never_relaunches(self):
        self.event('UserPromptSubmit');self.event('UserPromptSubmit')
        self.data['mission_complete']=True;self.freeze()
        self.assertEqual(self.event('Stop'),{})
        self.assertEqual(self.life.read()['attempts'],0)

    def test_rotation_cap_defers_without_blocking_stop_loop(self):
        self.event('UserPromptSubmit');self.event('UserPromptSubmit');self.freeze()
        self.life.change(lambda state:state.update(attempts=state['max_launches']))
        self.assertEqual(self.event('Stop'),{})
        self.assertIn('launch cap',self.life.read()['last_issue'])
        with patch.object(self.life,'rotate',side_effect=AssertionError('must not retry')):
            self.assertEqual(self.event('Stop',stop_hook_active=True),{})
            self.assertEqual(self.event('PreCompact'),{})

    def test_missing_launcher_defers_without_blocking_stop(self):
        self.event('UserPromptSubmit');self.event('UserPromptSubmit');self.freeze()
        with patch.object(self.life,'launch_plan',side_effect=ValueError('Native CLI is not installed')):
            self.assertEqual(self.event('Stop'),{})
        self.assertIn('not installed',self.life.read()['last_issue'])
        self.assertEqual(self.life.read()['attempts'],0)

    def test_reserved_packet_identity_cannot_be_overridden(self):
        self.data['scope']='unrelated'
        with self.assertRaises(ValueError):self.freeze()

    def test_posttool_invalidates_prepared_checkpoint(self):
        self.freeze()
        self.event('PostToolUse',tool_name='apply_patch',tool_input={'command':'patch'})
        self.assertEqual(self.life.read()['packet_turn'],-1)

    def test_hook_install_preserves_foreign_and_is_idempotent(self):
        path=self.project/'.codex/hooks.json';path.parent.mkdir()
        path.write_text(json.dumps({'hooks':{'Stop':[{'hooks':[{'type':'command','command':'existing-tool'}]}]},'description':'keep me'}))
        bridge.install_hooks(self.args);one=path.read_text()
        bridge.install_hooks(self.args);self.assertEqual(path.read_text(),one)
        self.assertIn('existing-tool',one)
        self.assertEqual(len(json.loads(one)['hooks']['Stop']),2)
        self.assertEqual(json.loads(one)['hooks']['SessionEnd'][0]['hooks'][0]['timeout'],3)

    def test_hook_backup_stays_outside_repository(self):
        self.args.host='claude'
        path=self.project/'.claude/settings.local.json';path.parent.mkdir()
        original={'env':{'EXAMPLE_PRIVATE_SETTING':'private fixture'}}
        path.write_text(json.dumps(original))
        bridge.install_hooks(self.args)
        self.assertEqual(list(path.parent.glob('*continuity-backup*')),[])
        backups=list((self.root/'vault/sessions/hook-backups').glob('*.json'))
        self.assertEqual(len(backups),1)
        self.assertEqual(json.loads(backups[0].read_text()),original)
        self.assertEqual(backups[0].stat().st_mode & 0o777,0o600)

    def test_foreign_project_and_subagent_ignored(self):
        before=self.life.read()['revision']
        event={'hook_event_name':'SessionStart','session_id':'other','cwd':str(self.root),'permission_mode':'default'}
        self.assertEqual(bridge.hook(self.life,self.args,event),{})
        self.event('SessionStart','other',agent_id='child')
        self.assertEqual(self.life.read()['revision'],before)

    def test_control_shell_chaining_rejected(self):
        command=__import__('shlex').join(bridge.invocation(self.args,'status'))
        self.assertTrue(bridge.control_command({'tool_name':'Bash','tool_input':{'command':command}}))
        self.assertFalse(bridge.control_command({'tool_name':'Bash','tool_input':{'command':command+'; touch bad'}}))

    def test_native_launch_quotes_paths_without_bypass_flags(self):
        self.freeze()
        with patch('continuity_core.lifecycle.shutil.which',side_effect=lambda name:'/usr/bin/'+name),patch.dict(os.environ,{'TMUX':'fixture'}):
            plan=self.life.launch_plan(self.life.read(),'a'*48)
        self.assertEqual(plan[:2],['tmux','new-window'])
        self.assertNotIn('bypass',str(plan))
        self.assertIn('CONTINUITY_HANDOFF_NONCE=',plan[-1])
        self.assertNotIn('resume --last',plan[-1])

    def test_fence_applies_to_project_subdirectories(self):
        self.reserve();child=self.project/'sub';child.mkdir()
        event={'hook_event_name':'PreToolUse','session_id':'owner','cwd':str(child),'permission_mode':'default','tool_name':'Bash','tool_input':{'command':'echo write'}}
        self.assertEqual(bridge.hook(self.life,self.args,event)['hookSpecificOutput']['permissionDecision'],'deny')

    def test_candidate_artifact_reader_works_in_new_process(self):
        self.candidate()
        command=bridge.invocation(self.args,'read-artifact')+['--path','work.py']
        response=json.loads(subprocess.check_output(command,text=True))
        self.assertEqual(response['content'],'print("fixture")\n')

    def test_context_gate_requires_fresh_exact_session_measurement(self):
        import time
        measurement={'session_id':'owner','used_tokens':70,'boundary_tokens':100,'next_turn_bound':10,'handoff_reserve':10,'observed_at':time.time(),'source':'synthetic host fixture'}
        self.life.record_context('owner',measurement)
        r=self.event('PreToolUse',tool_name='Bash',tool_input={'command':'echo ordinary'})
        self.assertEqual(r['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertEqual(self.event('PreToolUse',tool_name='Bash',tool_input={'command':'echo repair'}),{})
        measurement['observed_at']=time.time()-90
        with self.assertRaises(ValueError):self.life.record_context('owner',measurement)

    def test_claude_start_and_stop_formats(self):
        self.life.change(lambda state:state.update(host='claude'))
        self.args.host='claude'
        self.assertEqual(self.event('SessionStart')['hookSpecificOutput']['hookEventName'],'SessionStart')
        self.assertEqual(self.event('Stop')['decision'],'block')
        self.assertEqual(self.event('PreCompact'),{})

    def test_restart_and_sessionend_recovery(self):
        self.freeze();self.event('SessionEnd')
        restored=Lifecycle(self.root/'vault','project:fixture',self.project)
        try:
            self.assertTrue(restored.read()['owner_ended'])
            self.assertEqual(restored.verify_packet()['payload']['checkpoint']['goal'],'Finish offline cache')
            with self.assertRaises(ValueError): restored.recover('new','recover',False)
        finally: restored.close()

if __name__=='__main__': unittest.main()
