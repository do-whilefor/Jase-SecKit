"""Bounded, cancellable subprocess execution shared by the ASC adapter tools."""

import asyncio
import os
import signal
import subprocess
import weakref


MAX_CONCURRENT = 2
MAX_STDOUT_BYTES = 16 * 1024 * 1024
MAX_STDERR_BYTES = 1024 * 1024
DIAGNOSTIC_BYTES = 4000
_LIMITERS = weakref.WeakKeyDictionary()


def _limiter():
    loop = asyncio.get_running_loop()
    reference = _LIMITERS.get(loop)
    limiter = reference() if reference is not None else None
    if limiter is None:
        limiter = asyncio.Semaphore(MAX_CONCURRENT)
        # A semaphore can retain its loop. Weak values avoid retaining closed
        # test loops; active and queued calls hold the semaphore themselves.
        _LIMITERS[loop] = weakref.ref(limiter)
    return limiter


async def _stop_process(process):
    """Kill the analysis process and its workers, then reap the process."""
    if os.name == "nt":
        if process.returncode is None:
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/PID", str(process.pid), "/T", "/F",
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                try:
                    await asyncio.wait_for(killer.wait(), 5)
                except asyncio.TimeoutError:
                    killer.kill()
                    await killer.wait()
            except OSError:
                pass
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


async def _read_stream(stream, budget, name, overflow):
    result = bytearray()
    exceeded = False
    while data := await stream.read(65536):
        if not exceeded:
            if len(result) + len(data) > budget:
                exceeded = True
                if not overflow.done():
                    overflow.set_result((name, budget))
            else:
                result.extend(data)
        # Continue draining after overflow until tree cleanup finishes. This
        # prevents a paused pipe from blocking asyncio's process.wait().
    return bytes(result)


async def _write_input(process, data):
    if process.stdin is None:
        return
    try:
        process.stdin.write(data)
        await process.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        process.stdin.close()


async def _discard(stream):
    while await stream.read(65536):
        pass


async def _cleanup(process, tasks):
    try:
        await _stop_process(process)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _shield_cleanup(coroutine):
    task = asyncio.create_task(coroutine)
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Do not release a concurrency slot while its process is alive,
            # even if the client sends another cancellation during cleanup.
            continue
    return task.result()


async def _cleanup_spawn(spawn):
    try:
        process = await spawn
    except OSError:
        return
    drains = [asyncio.create_task(_discard(stream))
              for stream in (process.stdout, process.stderr)]
    await _cleanup(process, drains)


async def run_process(
    command: list[str], *, cwd: str, input_data: bytes | None = None,
    timeout: float = 60,
) -> str:
    """Run without a shell; enforce output budgets before command completion.

    The timeout covers an active process, not time queued for a concurrency
    slot. Public timeout configuration is validated by the adapter entry point.
    """
    async with _limiter():
        options = (
            {"creationflags": subprocess.CREATE_NO_WINDOW}
            if os.name == "nt" else {"start_new_session": True}
        )
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            *command, cwd=cwd,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
            stdin=asyncio.subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            **options,
        ))
        try:
            process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            await _shield_cleanup(_cleanup_spawn(spawn))
            raise
        except OSError as exc:
            raise RuntimeError(f"Cannot start ASC: {exc}") from exc

        overflow = asyncio.get_running_loop().create_future()
        tasks = [
            asyncio.create_task(_read_stream(process.stdout, MAX_STDOUT_BYTES, "stdout", overflow)),
            asyncio.create_task(_read_stream(process.stderr, MAX_STDERR_BYTES, "stderr", overflow)),
            asyncio.create_task(_write_input(process, input_data)),
            asyncio.create_task(process.wait()),
        ]
        finished = asyncio.gather(*tasks)
        try:
            done, _pending = await asyncio.wait(
                (finished, overflow), timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if overflow in done:
                stream, budget = overflow.result()
                raise RuntimeError(
                    f"ASC {stream} exceeds {budget} bytes; narrow the query or class prefix"
                )
            if finished not in done:
                raise RuntimeError(f"ASC timed out after {timeout:g} seconds")
            output, errors, _input, returncode = finished.result()
            if returncode:
                detail = errors[-DIAGNOSTIC_BYTES:].decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    f"ASC failed (exit {returncode}): {detail or 'no diagnostic output'}"
                )
            return output.decode("utf-8", errors="replace")
        except BaseException:
            await _shield_cleanup(_cleanup(process, tasks))
            raise
        finally:
            overflow.cancel()
            # Retrieve gather's exception as well as each task's result so
            # cancellation and pipe failures never become orphan warnings.
            await asyncio.gather(finished, return_exceptions=True)
