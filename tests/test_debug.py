"""_debug — 관측성 계약. warn 은 **두 경로 모두**로 나가야 한다(로컬 stderr + logging 레코드)."""
import logging

from briefing.core import _debug


def test_warn_writes_to_stderr(capsys):
    """로컬·테스트 계약(기존): DEBUG 무관하게 stderr 로 즉시 보인다."""
    _debug.warn("t", "무언가 빠졌다")
    err = capsys.readouterr().err
    assert "t" in err and "무언가 빠졌다" in err


def test_warn_emits_logging_record(caplog):
    """배포 계약(2026-07-27 발견): 컨테이너는 **Python logging 만** 수집한다.

    trafilatura 등 라이브러리의 logging 레코드는 CloudWatch 에 남는데 우리 raw print 는 남지 않았다
    (3시간 로그에 우리 warn 0건) — warn 의 존재 이유가 'silent failure 방지'인데 배포 환경에서
    정확히 silent 였다. 따라서 warn 은 logging 레코드도 함께 emit 해야 한다.
    """
    with caplog.at_level(logging.WARNING, logger="briefing"):
        _debug.warn("curate skip", "aitimes: TimeoutError")
    assert any(r.levelno == logging.WARNING and "aitimes: TimeoutError" in r.getMessage()
               for r in caplog.records), f"logging 레코드 없음: {caplog.records}"


def test_warn_does_not_double_print_locally(capsys):
    """logging 을 추가해도 로컬 stderr 출력이 중복되면 안 된다(NullHandler 로 lastResort 억제)."""
    _debug.warn("dup", "한 번만")
    assert capsys.readouterr().err.count("한 번만") == 1
