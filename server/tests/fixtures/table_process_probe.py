"""Dependency-free engine double for real multiprocessing start-method tests."""

import json
import multiprocessing
import os
import sys
from types import ModuleType

from utils import table_process

STATE = {"mode": None, "installs": 0, "modelInstalls": 0, "fields": None}


def policy(mode):
    STATE["mode"] = mode
    STATE["installs"] += 1

    def restore():
        STATE["mode"] = None
        STATE["installs"] -= 1

    return restore


def model_policy(value):
    from utils.model_policy import request_fields
    STATE["fields"] = request_fields(value)
    STATE["modelInstalls"] += 1

    def restore():
        STATE["fields"] = None
        STATE["modelInstalls"] -= 1

    return restore


def native_worker(queue):
    queue.put({**STATE, "pid": os.getpid()})


# This setup also runs when spawn reimports the main module. It supplies an
# engine double, not an installed policy: that is the worker adapter's job.
engine = ModuleType("pdf2zh_next.high_level")
engine._translate_wrapper = native_worker
package = ModuleType("pdf2zh_next")
package.high_level = engine
sys.modules["pdf2zh_next"] = package
sys.modules["pdf2zh_next.high_level"] = engine
table_process.install_table_policy = policy
table_process.table_policy_supported = lambda: True
table_process.install_model_policy = model_policy


def main():
    context = multiprocessing.get_context(sys.argv[1])
    queue = context.Queue()
    scenario = sys.argv[2] if len(sys.argv) > 2 else 'table'
    mode = None if scenario == 'model' else 'fixed'
    control = {'model': 'Qwen/Qwen3-test', 'thinkingEnabled': False} if scenario != 'table' else None
    restore = table_process.install_table_process_policy(mode, model_policy=control)
    expected = {"mode": mode, "installs": int(mode is not None),
                "modelInstalls": int(control is not None),
                "fields": {"enable_thinking": False} if control else None}
    try:
        child = context.Process(target=engine._translate_wrapper, args=(queue,))
        child.start()
        result = queue.get(timeout=20)
        child.join(timeout=20)
        assert child.exitcode == 0, child.exitcode
        assert result == {**expected, "pid": child.pid}, result
        assert child.pid != os.getpid()
        # The debug/in-process path is covered by the parent's own policy.
        native_worker(queue)
        parent_result = queue.get(timeout=5)
        assert all(parent_result[k] == v for k, v in expected.items())
        assert STATE == expected
    finally:
        restore()
        queue.close()
        queue.join_thread()
    assert engine._translate_wrapper is native_worker
    assert STATE == {"mode": None, "installs": 0, "modelInstalls": 0, "fields": None}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
