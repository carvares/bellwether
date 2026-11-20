@echo off
rem A made-up herdr-app for the Windows runner (the same answers as the shell script herdr-app beside it): `ls`
rem gives made-up agents, `do` answers null. Nothing else works.
if "%~1"=="ls" goto ls
if "%~1"=="do" (echo null& exit /b 0)
echo {"error": "made-up herdr-app: not here"} 1>&2
exit /b 1
:ls
echo {"spaces": [{"id": "sp1", "name": "Main", "tabs": [{"id": "tb1", "name": "1", "terminals": [
echo  {"terminal": "t1", "pane": "p1", "status": "blocked", "app": "claude-code", "name": "made-up reviewer", "sub_agents": []},
echo  {"terminal": "t2", "pane": "p2", "status": "working", "app": "codex", "name": "made-up builder", "sub_agents": []},
echo  {"terminal": "t3", "pane": "p3", "status": "done", "app": "opencode", "name": null, "sub_agents": []},
echo  {"terminal": "t4", "pane": "p4", "status": "idle", "app": "gemini", "name": "made-up planner", "sub_agents": []}]}]}]}
exit /b 0
