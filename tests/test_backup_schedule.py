import json
from datetime import datetime, timedelta, timezone

import pytest
from pkb import backup_client


@pytest.mark.parametrize('state,days,valid,expected', [
    ('success', 0, True, 0), ('unchanged', 0, True, 0),
    ('success', 1, True, 1), ('failed', 0, True, 1),
    ('success', 0, False, 1),
])
def test_daily_schedule(tmp_path, monkeypatch, state, days, valid, expected):
    status = tmp_path / 'runtime/cloud-backup/status.json'
    status.parent.mkdir(parents=True)
    status.write_text(json.dumps({'status': state,
        'last_check': (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(),
        'snapshot': str(tmp_path / 'snapshot'), 'fingerprint': 'sample'}))
    calls = []
    monkeypatch.setattr(backup_client, 'local_snapshot_valid', lambda *args: valid)
    monkeypatch.setattr(backup_client, 'backup', lambda **kwargs: calls.append(kwargs) or 0)
    assert backup_client.scheduled_backup(tmp_path) == 0
    assert len(calls) == expected


def test_missing_status_runs(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(backup_client, 'backup', lambda **kwargs: calls.append(kwargs) or 0)
    assert backup_client.scheduled_backup(tmp_path) == 0
    assert len(calls) == 1
