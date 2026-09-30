# -*- coding: utf-8 -*-
"""tools/trim_commit_guard.py 的判据测试：必须先能红，才许它当闸。

覆盖四种真实事故形状：
  1) 纯数据提交消失 -> 放行（filter-repo 退化裁剪的正常结果）
  2) 带走源码的提交消失 -> 判红（"不许拿丢历史换速度"的下界）
  3) 基线清单缺失 / 两份清单不同源 / 条数不闭合 -> 判据自己失明时必须拒绝放行，
     而不是"什么都没发生"地返回 0（这条是被上一版测试打出来的：父清单格式写错时，
     旧版只会逐条报"父清单缺这条"，报对了却把原因藏成了逐条噪声）
  4) 真 git + 真 filter-repo 跑一遍，钉住 %cI/%p/--name-only 的格式假设
"""
import contextlib
import io
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import trim_commit_guard as G  # noqa: E402

GUARD = os.path.join(ROOT, 'tools', 'trim_commit_guard.py')


def _before(*recs):
    """按 `git log --format='C|%H|%cI|%s' --name-only` 的形状造清单。"""
    lines = []
    for sha, date, subj, files in recs:
        lines.append('C|%s|%s|%s' % (sha, date, subj))
        lines.extend(files)
        lines.append('')
    return '\n'.join(lines)


def _parents(*pairs):
    """按 `git log --format='P|%H|%p'` 的形状造父清单：P|<sha>|<父 sha...>"""
    return ''.join('P|%s|%s\n' % (sha, ' '.join(ps)) for sha, ps in pairs)


def _run_guard(before, parents, after_log, count='0'):
    """只测判定逻辑：把 git 的两个出口 monkeypatch 掉，stdout 收进 StringIO。"""
    def fake_git(args):
        if args[:2] == ['rev-list', '--count']:
            return count + '\n'
        return after_log

    real = G.git
    G.git = fake_git
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = G.main(['--before', str(before), '--parents', str(parents)])
    finally:
        G.git = real
    return rc, buf.getvalue()


def test_pruned_path_rules():
    assert G.is_pruned('rss-data-1.js') is True
    assert G.is_pruned('rss_history_3.json') is True
    assert G.is_pruned('rss_api_snapshot.json') is True
    assert G.is_pruned('rss_cache.json') is True
    # chunk 0 是故意留在库里的，判据不能把它算成"该消失"
    assert G.is_pruned('rss-data-0.js') is False
    assert G.is_pruned('build_rss_aggregator.py') is False


def test_parse_before_keeps_pipe_in_subject():
    recs = G.parse_before(_before(('a' * 40, '2026-09-30T10:00:00+08:00', 'fix: a|b 管道标题', ['x.py'])))
    assert len(recs) == 1
    assert recs[0]['key'] == ('2026-09-30T10:00:00+08:00', 'fix: a|b 管道标题')
    assert recs[0]['files'] == ['x.py']


def test_dropped_data_only_is_allowed(tmp_path):
    b = tmp_path / '.commits_before.txt'
    p = tmp_path / '.commits_parents.txt'
    b.write_text(_before(('b' * 40, '2026-09-30T10:00:00+08:00',
                          'chore(ci): 数据自提', ['rss-data-1.js', 'rss_cache.json'])), encoding='utf-8')
    p.write_text(_parents(('b' * 40, ['s1', 's2'])), encoding='utf-8')
    rc, out = _run_guard(b, p, after_log='')
    assert rc == 0, out
    assert 'OK-纯数据' in out
    assert '闸零通过' in out


def test_dropped_source_commit_is_rejected(tmp_path):
    """变异体：消失的那条改了源码 —— 这条必须打死，否则整道闸是装饰品。"""
    b = tmp_path / '.commits_before.txt'
    p = tmp_path / '.commits_parents.txt'
    b.write_text(_before(('c' * 40, '2026-09-30T11:00:00+08:00',
                          'feat: 真实功能改动', ['build_rss_aggregator.py', 'rss-data-1.js'])), encoding='utf-8')
    p.write_text(_parents(('c' * 40, ['s1'])), encoding='utf-8')
    rc, out = _run_guard(b, p, after_log='')
    assert rc == 1, out
    assert 'BAD-含非数据文件' in out
    assert '::error::' in out


def test_empty_non_merge_without_files_is_rejected(tmp_path):
    b = tmp_path / '.commits_before.txt'
    p = tmp_path / '.commits_parents.txt'
    b.write_text(_before(('d' * 40, '2026-09-30T12:00:00+08:00', 'x', [])), encoding='utf-8')
    p.write_text(_parents(('d' * 40, ['s1'])), encoding='utf-8')
    rc, out = _run_guard(b, p, after_log='')
    assert rc == 1, out
    assert 'BAD-无文件非合并' in out


def test_empty_merge_without_files_is_allowed(tmp_path):
    b = tmp_path / '.commits_before.txt'
    p = tmp_path / '.commits_parents.txt'
    b.write_text(_before(('e' * 40, '2026-09-30T12:30:00+08:00', 'Merge branch x', [])), encoding='utf-8')
    p.write_text(_parents(('e' * 40, ['s1', 's2'])), encoding='utf-8')
    rc, out = _run_guard(b, p, after_log='')
    assert rc == 0, out
    assert 'OK-空合并' in out


def test_missing_baseline_is_not_silently_green(tmp_path):
    rc, out = _run_guard(tmp_path / 'nope.txt', tmp_path / 'nope2.txt', after_log='')
    assert rc == 1, out
    assert '缺基线清单' in out


def test_parents_before_different_sizes_block(tmp_path):
    """两份清单不同源（上一版的真实翻车形状）：必须报"父清单 != 基线"，不许逐条糊弄。"""
    b = tmp_path / '.commits_before.txt'
    p = tmp_path / '.commits_parents.txt'
    b.write_text(_before(('f' * 40, '2026-09-30T13:00:00+08:00', 'keep', ['x.py'])), encoding='utf-8')
    p.write_text('', encoding='utf-8')          # 父清单空 = 上一版 fixture 写错格式的效果
    rc, out = _run_guard(b, p, after_log='')
    assert rc == 1, out
    assert '父清单' in out and '判据失明' in out


def test_count_mismatch_blocks(tmp_path):
    """基线条数 != 重写后 + 消失数 => 判据失明，拒绝放行。"""
    b = tmp_path / '.commits_before.txt'
    p = tmp_path / '.commits_parents.txt'
    b.write_text(_before(
        ('g' * 40, '2026-09-30T13:00:00+08:00', 'keep', ['x.py']),
        ('h' * 40, '2026-09-30T13:01:00+08:00', 'gone-data', ['rss_history.json']),
    ), encoding='utf-8')
    p.write_text(_parents(('g' * 40, ['s1']), ('h' * 40, ['s1'])), encoding='utf-8')
    rc, out = _run_guard(b, p, after_log='2026-09-30T13:00:00+08:00\tK\tkeep\n', count='9')
    assert rc == 1, out
    assert '条数对不上' in out


def _has_filter_repo():
    try:
        return subprocess.run(['git', 'filter-repo', '--version'],
                              capture_output=True, text=True).returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(not _has_filter_repo(), reason='本机没有 git-filter-repo，格式假设那一段测不了')
def test_real_git_and_filter_repo_end_to_end(tmp_path):
    """真仓库走一遍：抓基线 -> filter-repo 剔族 -> 闸必须放行，且源码提交还在。

    这条钉的是格式假设（%cI / %p / --name-only 的输出形状）。单测全绿也照样可能是瞎闸，
    因为 fixture 是我照着想象造的；所以必须拿真 git 对一次。
    """
    env = dict(os.environ)
    env.update({'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@e', 'GIT_COMMITTER_NAME': 'T',
                'GIT_COMMITTER_EMAIL': 't@e', 'PYTHONIOENCODING': 'utf-8'})

    def run(*a):
        return subprocess.run(list(a), cwd=str(tmp_path), env=env,
                              capture_output=True, text=True, encoding='utf-8', errors='replace')

    run('git', 'init', '-q', str(tmp_path))
    for i, (name, body) in enumerate([
        ('keep.py', 'print(1)'),
        ('rss-data-1.js', 'x' * 100),
        ('rss_history_0.json', '{}'),
        ('rss_cache.json', '{}'),
        ('final.py', 'print(2)'),
    ]):
        (tmp_path / name).write_text(body, encoding='utf-8')
        run('git', 'add', name)
        run('git', 'commit', '-q', '-m', 'c%d %s' % (i, name))
    assert int(run('git', 'rev-list', '--count', 'HEAD').stdout.strip()) == 5
    (tmp_path / '.commits_before.txt').write_text(
        run('git', 'log', '--format=C|%H|%cI|%s', '--name-only').stdout, encoding='utf-8')
    (tmp_path / '.commits_parents.txt').write_text(
        run('git', 'log', '--format=P|%H|%p').stdout, encoding='utf-8')
    r = run('git', 'filter-repo', '--force', '--invert-paths',
            '--path-glob', 'rss-data-[1-9]*.js', '--path-glob', 'rss_history*.json',
            '--path-glob', 'rss_cache.json')
    assert r.returncode == 0, r.stdout + r.stderr
    assert int(run('git', 'rev-list', '--count', 'HEAD').stdout.strip()) == 2, \
        '退化提交应被裁掉，只剩两条源码提交'
    out = subprocess.run([sys.executable, GUARD], cwd=str(tmp_path), env=env,
                         capture_output=True, text=True, encoding='utf-8', errors='replace')
    body = out.stdout + out.stderr
    assert out.returncode == 0, body
    assert body.count('OK-纯数据') == 3, body
    assert '::error::' not in body, body
    # 反向断言：把一条源码提交伪造成"消失了"，真流程里这道闸必须挡下来
    bad = (tmp_path / '.commits_before.txt').read_text(encoding='utf-8') + _before(
        ('1' * 40, '2026-09-30T09:00:00+08:00', 'fake-source-loss', ['keep.py']))
    (tmp_path / '.commits_before.txt').write_text(bad, encoding='utf-8')
    pm = (tmp_path / '.commits_parents.txt').read_text(encoding='utf-8') + _parents(('1' * 40, ['s1']))
    (tmp_path / '.commits_parents.txt').write_text(pm, encoding='utf-8')
    out2 = subprocess.run([sys.executable, GUARD], cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert out2.returncode == 1, out2.stdout + out2.stderr
    assert 'BAD-含非数据文件' in out2.stdout, out2.stdout
