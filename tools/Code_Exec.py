import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
import textwrap
import importlib
import numpy as np

import json
import pickle
import scipy
import multiprocessing as mp
import io
import sys
import time
import contextlib
import traceback
from datetime import datetime

############################################################################################################################
import io
import textwrap
import traceback
from contextlib import redirect_stdout, redirect_stderr


def run_code(code, functions_and_var=None):
    if functions_and_var is None:
        functions_and_var = {}

    # 1. Create a FRESH namespace for this specific run
    # We include __builtins__ so the code has access to print, range, etc.
    env = {"__builtins__": __builtins__}

    # 2. Inject your specific functions or variables into this fresh env
    env.update(functions_and_var)

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    successed = True
    exec_error = None

    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        try:
            # 3. Pass 'env' as both globals and locals to isolate it
            exec(textwrap.dedent(code), env)
        except Exception:
            successed = False
            exec_error = traceback.format_exc()

    captured_stdout = out_buf.getvalue()
    captured_stderr = err_buf.getvalue()

    # Optional: Debugging prints
    if not successed:
        print("=== Captured stderr ===")
        print(captured_stderr)
        if exec_error:
            print("=== Caught Exception Traceback ===")
            print(exec_error)

    return successed, captured_stdout, exec_error if exec_error else captured_stderr
#################################################################################################################################
def run_code_timeout(code, functions_and_var=None, time_out=5):
    """
    Run run_code(code, functions_and_var) for up to `time_out` seconds.

    If it finishes in time:
        returns the value returned by run_code.
    If it times out:
        returns (printed_text_so_far, "Timed out").
    """
    if functions_and_var is None:
        functions_and_var = {}

    ctx = mp.get_context("spawn")  # robust across platforms
    out_q = ctx.Queue()            # for streamed stdout/stderr from child
    res_q = ctx.Queue()            # for final result / error from child

    def _worker(code, fvars, out_q, res_q):
        class _QueueWriter(io.TextIOBase):
            def __init__(self, q, stream_name):
                self.q = q
                self.stream_name = stream_name
            def write(self, s):
                if s:
                    # send chunks as they are written
                    self.q.put((self.stream_name, s))
                return len(s)
            def flush(self):  # no-op; present for API compatibility
                pass

        stdout_proxy = _QueueWriter(out_q, "stdout")
        stderr_proxy = _QueueWriter(out_q, "stderr")

        with contextlib.redirect_stdout(stdout_proxy), contextlib.redirect_stderr(stderr_proxy):
            try:
                result = run_code(code, fvars)
                res_q.put(("ok", result))
            except Exception:
                # print the traceback to the captured stream, and report error
                traceback.print_exc()
                res_q.put(("err", None))

    proc = ctx.Process(target=_worker, args=(code, functions_and_var, out_q, res_q))
    proc.start()

    start = time.time()
    captured_chunks = []
    result = None

    # Poll for result while streaming out any printed text
    while True:
        remaining = time_out - (time.time() - start)
        if remaining <= 0:
            break

        # Try to get a result quickly (tiny timeout to stay responsive to prints)
        try:
            result = res_q.get(timeout=min(0.1, max(0.01, remaining)))
            break
        except Exception:
            pass

        # Drain any printed output without blocking
        while True:
            try:
                _stream, chunk = out_q.get_nowait()
                captured_chunks.append(chunk)
            except Exception:
                break

        time.sleep(0.01)  # cooperative pause

    # Drain any last printed output we already have
    while True:
        try:
            _stream, chunk = out_q.get_nowait()
            captured_chunks.append(chunk)
        except Exception:
            break

    printed_text = "".join(captured_chunks)

    if result is not None:
        # Child finished in time: return run_code's value
        status, value = result
        proc.join(timeout=0.1)
        if status == "ok":
            return value
        else:
            # If run_code raised, we return what was printed so far and "Timed out"
            # would be misleading; instead propagate a RuntimeError with captured output.
            raise RuntimeError("run_code raised an exception.\n\nCaptured output:\n" + printed_text)
    else:
        # Timed out: kill child and return printed output + "Timed out"
        proc.terminate()
        proc.join()
        return False, printed_text, "Error: The code is either get stuck or take very very  long to run."
############################################################################################################################
# Check if code is finished in a given time time_out in seconds
import multiprocessing as mp

def run_code_check_time(code, functions_and_var=None, time_out=5):
    print("Check running time. \nTime out in seconds:",time_out,"\nStarting time",datetime.now().strftime("%H:%M:%S"))
    if functions_and_var is None:
        functions_and_var = {}

    # Prefer 'fork' on Unix to avoid spawn-import headaches; fall back to 'spawn' elsewhere.
    try:
        ctx = mp.get_context("fork")
    except ValueError:
        ctx = mp.get_context("spawn")

    # Worker must be a top-level function when using 'spawn'
    def _worker(c, env):
        # run_code must also be importable at module level (not nested)
        run_code(c, env)

    p = ctx.Process(target=_worker, args=(code, functions_and_var))
    p.start()
    p.join(time_out)

    if p.is_alive():
        p.terminate()
        p.join()
        print("\n\nExceed Time limits\n\n")
        return False
    print("\n\nFinished on time\n\n")
    return True

#############################################################################################################################
if __name__=="__main__":
    # code_str = """
    # import torch
    # x=torch.zeros([5,5])+3
    # print(x)
    # def greet(name):
    #     print(f"Hello, {name}!")
    #
    # greet("Alice")
    # """
    #
    # # Directly
    # exec(code_str)
#

    # Doesnt deal with error messages
    code_str = """
    import torch
    x=torch.zeros([5,5])+3
    print(x)
    def greet(name):
        print(f"Hello, {name}!")
    
    greet("Alice")
    """
    successed, captured_stdout, captured_stderr = run_code(code_str)

    # Directly
    exec(textwrap.dedent(code_str))

    # Or compile first (gives more control)
    compiled = compile(textwrap.dedent(code_str), filename="<dynamic>", mode="exec")
    exec(compiled)