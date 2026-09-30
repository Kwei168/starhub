#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trim_commit_guard —— 证明"历史重写后少掉的那些提交，每一个都没有带走人写的代码"。

为什么需要它（2026-09-30 实测逼出来的）：repo-trim 的 dry-run 里 `.git` 从 5.3G 掉到 368M 很漂亮，
但提交数 2039 -> 2037 悄悄少了 2 条。原先我只钉了"路径不许少"——路径守恒对提交守恒毫无约束：
git-filter-repo 默认把改动全落在被剔族里的提交当退化提交丢掉。少 2 条可以接受，
前提是逐条说得清"少的是谁、它当时改过哪些文件"。所以这道闸不问"少了几条"，问每一条少的下落。

用法（在仓库根、重写之后运行）：python3 tools/trim_commit_guard.py
前置（repo-trim.yml 的"记录基线"步骤必须在重写之前抓好）：
    git log --format='C|%H|%cI|%s' --name-only > .commits_before.txt
    git log --format='P|%H|%p'                  > .commits_parents.txt
退出码 0 = 每一条消失都可解释；1 = 说不清，绝不许推送。
"""
import argparse
import io
import os
import subprocess
import sys
from collections import Counter

KEEP_ALWAYS = ('rss-data-0.js',)          # chunk 0 故意留在库里：真实分块测试读已入库副本
PRUNED_PREFIX = ('rss-data-', 'rss_history', 'rss_api_snapshot')
PRUNED_EXACT = ('rss_cache.json',)


def is_pruned(path):
    """这个路径是不是本次重写要剔掉的死数据族。chunk 0 明确不算。"""
    if path in KEEP_ALWAYS:
        return False
    if path in PRUNED_EXACT:
        return True
    return path.startswith(PRUNED_PREFIX)


def parse_before(text):
    """.commits_before.txt -> [{'sha','key':(committer_iso, subject),'files':[...]}]

    由 `git log --format='C|%%H|%%cI|%%s' --name-only` 产生：一行 C| 头 + 若干文件名 + 空行。
    标题里出现 '|' 不会被切碎（split 限 3 次，标题整段落在最后一项）。
    merge 提交 git 默认不列文件，所以 files 可能为空——空不等于没问题，另按父提交数判定。
    """
    out, cur = [], None
    for line in text.split('\n'):
        if line.startswith('C|'):
            p = line.split('|', 3)
            if len(p) < 4:
                continue
            cur = {'sha': p[1], 'key': (p[2], p[3]), 'files': []}
            out.append(cur)
        elif cur is not None and line.strip():
            cur['files'].append(line.strip())
    return out


def parse_parents(text):
    """.commits_parents.txt（`P|<sha>|<父 sha...>`）-> {sha: [父, ...]}；空列表=根提交，>=2=merge"""
    m = {}
    for line in text.split('\n'):
        if not line.startswith('P|'):
            continue
        p = line.split('|', 2)
        if len(p) < 3:
            continue
        m[p[1]] = p[2].split() if p[2].strip() else []
    return m


def after_keys(text):
    """重写后 `git log --format=%cI\\t%an\\t%s` 的计数表。filter-repo 保留作者/时间/标题，
    所以 (committer 时间, 标题) 足以当同一提交的对应记号；用计数不用集合，防同名标题互相吞。"""
    c = Counter()
    for line in text.split('\n'):
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        c[(parts[0], '\t'.join(parts[2:]))] += 1
    return c


def find_dropped(before, after):
    """返回重写后找不到对应记录的提交。按 key 剩余次数逐条扣减，重复标题也能对上数量。"""
    left = Counter(b['key'] for b in before)
    dropped = []
    for b in before:
        k = b['key']
        if left[k] > after.get(k, 0):
            dropped.append(b)
        left[k] -= 1
    return dropped


def verdict(rec, parents):
    """一条消失的提交 -> ('OK-*'|'BAD-*', 理由)。"""
    files = rec['files']
    if rec['sha'] not in parents:
        return 'BAD-父清单缺这条', '基线没抓到它的父提交，无法判断是不是合并'
    ps = parents[rec['sha']]
    if files and all(is_pruned(f) for f in files):
        return 'OK-纯数据', '%d 个文件全在被剔族里' % len(files)
    if not files and len(ps) >= 2:
        return 'OK-空合并', 'merge 且自身不改任何文件，两个父都在世'
    if not files:
        return 'BAD-无文件非合并', '不是 merge 却不列文件，说不清它带走了什么'
    return 'BAD-含非数据文件', '留下了 %s' % ', '.join(f for f in files if not is_pruned(f))[:120]


def git(args):
    return subprocess.run(['git'] + list(args), capture_output=True,
                          text=True, encoding='utf-8', errors='replace').stdout


def main(argv=None):
    # 输出必须是 UTF-8：Windows 控制台默认 cp936，中文判定标签会糊成一屏 U+FFFD，
    # 让读日志的人（和读子进程输出的测试）都看不见真相。
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--before', default='.commits_before.txt')
    ap.add_argument('--parents', default='.commits_parents.txt')
    a = ap.parse_args(argv)
    for f in (a.before, a.parents):
        if not os.path.exists(f):
            print('::error::缺基线清单 %s（应在重写前由"记录基线"步骤生成），判据无法成立，绝不推送' % f)
            return 1
    before = parse_before(io.open(a.before, encoding='utf-8', errors='replace').read())
    parents = parse_parents(io.open(a.parents, encoding='utf-8', errors='replace').read())
    after = after_keys(git(['log', '--format=%cI\t%an\t%s']))
    n_after = int((git(['rev-list', '--count', 'HEAD']).strip() or '0'))
    dropped = find_dropped(before, after)
    print('基线清单解析出提交 %d 条，父清单 %d 条；重写后 HEAD 提交数 %d' % (
        len(before), len(parents), n_after))
    # 三份计数必须闭合，否则这道闸本身是瞎的：宁可挡住也不放行
    if len(parents) != len(before):
        print('::error::父清单 %d 条 != 基线提交 %d 条，两份清单不同源，判据失明，绝不推送' % (
            len(parents), len(before)))
        return 1
    if len(before) != n_after + len(dropped):
        print('::error::条数对不上（基线 %d != 重写后 %d + 消失 %d），判据自身不可信，绝不推送' % (
            len(before), n_after, len(dropped)))
        return 1
    print('重写后找不到对应记录的提交 %d 条，逐条判定：' % len(dropped))
    bad = []
    for rec in dropped:
        tag, why = verdict(rec, parents)
        print('   [%-16s] %s %s  %s' % (tag, rec['sha'][:10], rec['key'][0][:19], why))
        if tag.startswith('BAD'):
            bad.append(rec['sha'])
    if bad:
        print('::error::有 %d 条提交带走了不该带的东西：%s —— 绝不推送' % (
            len(bad), ','.join(x[:10] for x in bad)))
        return 1
    if not dropped:
        print('   （一条没少，提交数守恒）')
    print('闸零通过：消失的提交全部可解释为纯数据或空合并')
    return 0


if __name__ == '__main__':
    sys.exit(main())
