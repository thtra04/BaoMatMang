import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safepay.seed import DemoEnv  # noqa: E402


@pytest.fixture
def env():
    return DemoEnv()


@pytest.fixture
def ids(env):
    """Mã người thụ hưởng: MP = Bao Bì Minh Phát (quen), SV = Vận tải Sao Việt, AT = Phần mềm An Tâm (chưa từng thanh toán)."""
    return {"MP": env.bene["Công ty TNHH Bao Bì Minh Phát"], "SV": env.bene["Công ty CP Vận tải Sao Việt"],
            "AT": env.bene["Công ty TNHH Phần mềm An Tâm"]}
