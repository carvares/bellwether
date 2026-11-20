@echo off
rem A made-up herdr-core for the Windows runner (the same answers as the shell script herdr-core beside it): `ls
rem --json` and `get` give made-up terminals, `events --json` is a slow stream of heartbeats (one now, then one each
rem 2 seconds) that lives until it is ended. The wait is a ping of this machine: `timeout` needs a console input.
if "%~1"=="ls" (echo {"terminals": [{"address": "t1", "agent": "claude-code", "state": "live", "status": "blocked", "turn": 1}]}& exit /b 0)
if "%~1"=="get" (echo {"address": "%~2", "state": "live", "pid": 0, "created_ms": 0, "title": ""}& exit /b 0)
if "%~1"=="events" goto events
echo {"error": {"kind": "unknown"}} 1>&2
exit /b 1
:events
echo {"jsonrpc":"2.0","method":"heartbeat","params":{}}
ping -n 3 127.0.0.1 >nul
goto events
