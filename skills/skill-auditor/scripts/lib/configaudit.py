"""Review of hook configurations, shipped settings files, and MCP server definitions."""

from __future__ import annotations

import os
import re
from typing import Any

from .catalog import LINE_RULES
from .model import Ctx, Finding, kind_of
from .text import scan_re
from .util import (
    as_list,
    as_text,
    get_key,
    is_absolute_path,
    iter_items,
    parse_json,
    read_audited_bytes,
    relative_to,
)

__all__ = [
    'audit_config_files',
    'audit_hooks',
    'audit_mcp',
    'audit_settings',
    'mentions_injection',
]


KNOWN_EVENTS: frozenset[str] = frozenset({
    'Setup', 'SessionStart', 'SessionEnd', 'UserPromptSubmit', 'UserPromptExpansion', 'Stop',
    'StopFailure',
    'PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'PostToolBatch', 'PermissionRequest',
    'PermissionDenied',
    'Notification', 'MessageDisplay', 'SubagentStart', 'SubagentStop', 'TaskCreated',
    'TaskCompleted',
    'TeammateIdle', 'InstructionsLoaded', 'ConfigChange', 'CwdChanged', 'DirectoryAdded',
    'FileChanged',
    'WorktreeCreate', 'WorktreeRemove', 'PreCompact', 'PostCompact', 'PreModelSwitch',
    'PostModelSwitch',
    'Elicitation', 'ElicitationResult',
})

AMBIENT_EVENTS: frozenset[str] = frozenset({
    'UserPromptSubmit', 'UserPromptExpansion', 'SessionStart', 'PostToolBatch',
    'InstructionsLoaded',
    'ConfigChange', 'CwdChanged', 'FileChanged',
})

GUARD_EVENTS: frozenset[str] = frozenset({
    'PreToolUse', 'Stop', 'SubagentStop', 'UserPromptSubmit', 'PermissionRequest', 'ConfigChange',
})

HANDLER_TYPES: frozenset[str] = frozenset({'command', 'http', 'mcp_tool', 'prompt', 'agent'})

RE_SETTINGS_FILE: re.Pattern[str] = scan_re(r'(^|\/)(\.claude\/)?settings(\.local)?\.json$', 'i')

RE_MCP_FILE: re.Pattern[str] = scan_re(r'(^|\/)(\.mcp\.json|mcp\.json|mcp[_-]?servers?\.json|\.mcp\/[^/]+\.json)$', 'i')

RE_PLUGIN_JSON: re.Pattern[str] = scan_re(r'plugin\.json$', 'i')

RE_MCP_SERVERS_WORD: re.Pattern[str] = scan_re(r'mcpServers')

RE_INJECTION_FAMILY: re.Pattern[str] = scan_re(r'^(INJ|REF|LEAK)')

# Hooks, settings, MCP.
RE_MATCHER_SPECIAL: re.Pattern[str] = scan_re(r'[^A-Za-z0-9_\-| ]')

RE_QUIET_EVENT: re.Pattern[str] = scan_re(r'^(Stop|SessionEnd|Notification)$')

RE_PROJECT_DIR_VAR: re.Pattern[str] = scan_re(r'\$\{?CLAUDE_PROJECT_DIR\}?')

RE_SCRIPT_EXT: re.Pattern[str] = scan_re(r'\.(js|mjs|py|sh|ps1)\b')

RE_NET_TOOL_CMD: re.Pattern[str] = scan_re(r'\b(curl|wget|scp|rsync|nc)\b|Invoke-(WebRequest|RestMethod)', 'i')

RE_HOOK_SCRIPT: re.Pattern[str] = scan_re(r'([^\s"\']+\.(?:js|mjs|cjs|py|sh|ps1))')

RE_PLUGIN_ROOT_VAR: re.Pattern[str] = scan_re(r'\$\{?(CLAUDE_PLUGIN_ROOT|CLAUDE_SKILL_DIR)\}?')

RE_PROJECT_DIR_WORD: re.Pattern[str] = scan_re(r'CLAUDE_PROJECT_DIR')

RE_ABSOLUTE_PATH: re.Pattern[str] = scan_re(r'^[A-Za-z]:[\\/]|^\/')

RE_PLUGIN_ROOT_WORD: re.Pattern[str] = scan_re(r'CLAUDE_(PLUGIN_ROOT|SKILL_DIR)')

RE_STOP_ACTIVE: re.Pattern[str] = scan_re(r'stop_hook_active')

RE_EXIT_2: re.Pattern[str] = scan_re(r'exit\s*\(\s*2\s*\)|exit\s+2\b|exitCode\s*=\s*2|sys\.exit\(\s*2\s*\)')

RE_DECISION_BLOCK: re.Pattern[str] = scan_re(r'permissionDecision|decision\s*[:=]\s*[\'"](block|deny)|"decision"\s*:\s*"block"')

RE_EXIT_1: re.Pattern[str] = scan_re(r'exit\s*\(\s*1\s*\)|exit\s+1\b|exitCode\s*=\s*1|sys\.exit\(\s*1\s*\)')

RE_BROAD_ALLOW: re.Pattern[str] = scan_re(
    r'^(\*|Bash|Bash\(\*\)|Write|Edit|WebFetch|mcp__.*|Read\(\/\*\*\)|Read\(~?\/?\*\*?\))$')

RE_BROAD_BASH: re.Pattern[str] = scan_re(r'^Bash\((sh|bash|curl|wget|python3?|node|sudo|rm)\b')

RE_RISKY_MODE: re.Pattern[str] = scan_re(r'^(bypassPermissions|acceptEdits|dontAsk|auto)$')

RE_TOP_LEVEL_DIR: re.Pattern[str] = scan_re(r'^(\/|~|[A-Za-z]:\\?$)')

RE_TRAILING_SLASHES: re.Pattern[str] = scan_re(r'[\\/]+$')

RE_PATH_SEP: re.Pattern[str] = scan_re(r'[\\/]')

RE_ENDPOINT_ENV: re.Pattern[str] = scan_re(
    r'^(ANTHROPIC_BASE_URL|ANTHROPIC_AUTH_TOKEN|ANTHROPIC_API_KEY|HTTPS?_PROXY|ALL_PROXY|NODE_EXTRA_CA_CERTS'
    r'|NODE_TLS_REJECT_UNAUTHORIZED|CLAUDE_CODE_USE_\w+|AWS_ENDPOINT_URL\w*|OPENAI_BASE_URL)$', 'i')

RE_TOKEN_KEY: re.Pattern[str] = scan_re(r'TOKEN|KEY', 'i')

RE_PACKAGE_RUNNER: re.Pattern[str] = scan_re(r'^(npx|uvx|pipx|bunx|pnpm|yarn|docker|podman|deno)$', 'i')

RE_RUNNER_SUBCOMMAND: re.Pattern[str] = scan_re(r'^(run|dlx|exec|x|install|pull)$')

RE_PINNED: re.Pattern[str] = scan_re(r'@\d|:[\w.-]*\d|@sha256:|==')

RE_LEADING_AT: re.Pattern[str] = scan_re(r'^@')

RE_SHELL_BINARY: re.Pattern[str] = scan_re(r'^(sh|bash|zsh|cmd(\.exe)?|powershell(\.exe)?|pwsh)$', 'i')

RE_SHELL_FLAG: re.Pattern[str] = scan_re(r'^(-c|\/c|-Command|-EncodedCommand)$', 'i')

RE_PLAIN_HTTP_URL: re.Pattern[str] = scan_re(r'^http:\/\/', 'i')

RE_LOCAL_HTTP_URL: re.Pattern[str] = scan_re(r'^http:\/\/(localhost|127\.0\.0\.1|\[::1\])', 'i')

RE_IP_HTTP_URL: re.Pattern[str] = scan_re(r'^https?:\/\/\d+\.\d+\.\d+\.\d+')

RE_ENV_REFERENCE: re.Pattern[str] = scan_re(r'^\$\{?[\w:-]+\}?$')

RE_SECRET_PREFIX: re.Pattern[str] = scan_re(r'^(sk-|ghp_|gho_|github_pat_|xox[abp]-|AKIA|AIza|eyJ|glpat-|npm_)')

RE_SECRET_KEY_NAME: re.Pattern[str] = scan_re(r'(token|secret|password|api[_-]?key|authorization)', 'i')

RE_BEARER_VAR: re.Pattern[str] = scan_re(r'^(Bearer\s+)?\$')


def audit_config_files(ctx: Ctx) -> None:
    """Review hook configs, settings files, and MCP configs found among the texts."""
    for rel in list(ctx.texts):
        text = ctx.texts[rel]
        if kind_of(rel) == 'hook-config':
            audit_hooks(ctx, rel, text)
        if RE_SETTINGS_FILE.search(rel):
            audit_settings(ctx, rel, text)
        if RE_MCP_FILE.search(rel) or (
            RE_PLUGIN_JSON.search(rel) and RE_MCP_SERVERS_WORD.search(text)
        ):
            audit_mcp(ctx, rel, text)


def audit_hooks(ctx: Ctx, rel: str, text: str) -> None:
    """Review a hooks configuration file: events, matchers, handlers, scripts, blocking."""
    try:
        obj = parse_json(text)
    except ValueError as exc:
        ctx.add(config_finding(rel, 0.95, str(exc), 'HKS01'))
        return
    inner = get_key(obj, 'hooks')
    audit_hook_events(ctx, rel, inner if isinstance(inner, (dict, list)) else obj)


def audit_hook_group(ctx: Ctx, rel: str, event: str, g: dict[str, Any]) -> None:
    """Review one matcher group of a hooks configuration."""
    matcher = g.get('matcher')
    if matcher:
        m = as_text(matcher)
        if RE_MATCHER_SPECIAL.search(m):
            try:
                re.compile(m)
            except (re.error, RecursionError, OverflowError):
                ctx.add(config_finding(rel, 0.9, 'matcher: ' + m, 'HKS02', severity='high'))
    for h in as_list(g.get('hooks')):
        if isinstance(h, dict):
            audit_hook_handler(ctx, rel, event, matcher, h)


def audit_hook_handler(ctx: Ctx, rel: str, event: str, matcher: Any, h: dict[str, Any]) -> None:
    """Review one hook handler: type, scope, timeout, command, and the script it runs."""
    cmd = handler_command(h)
    fallback = cmd or (as_text(h['url']) if h.get('url') else '') or (
        as_text(h['prompt']) if h.get('prompt') else ''
    )
    matcher_str = as_text(matcher) if matcher else '*'
    type_text = as_text(h.get('type', 'undefined'))
    ctx.hook_summary.append(f'{event}|{matcher_str}|{type_text}|{fallback}'[:200])
    htype = h.get('type')
    if not (isinstance(htype, str) and htype in HANDLER_TYPES):
        ctx.add(config_finding(rel, 0.8, 'handler type: ' + type_text, 'HKS02'))
    if htype in ('prompt', 'agent'):
        ctx.add(config_finding(rel, 0.7, event, 'HKS09'))
    if htype == 'http':
        ctx.add(config_finding(rel, 0.85, as_text(h.get('url', 'undefined')), 'HKS08'))
    if (not matcher or matcher == '*') and not h.get('if') and not RE_QUIET_EVENT.search(event):
        scope = 'tool call' if event in ('PreToolUse', 'PostToolUse') else 'event'
        ctx.add(config_finding(rel, 0.6, f'{event} with no matcher fires on every {scope}', 'HKS11',
                               severity='low' if event in AMBIENT_EVENTS else 'medium'))
    if htype == 'command':
        audit_command_handler(ctx, rel, event, h, cmd)


def audit_hook_script(ctx: Ctx, rel: str, event: str, cmd: str) -> None:
    """Check the script a hook command runs: existence, absolute paths, and guard behavior."""
    sm = RE_HOOK_SCRIPT.search(cmd)
    if not sm:
        return
    script = sm.group(1)
    root_dir = ctx.dir.replace('\\', '/')
    p = RE_PLUGIN_ROOT_VAR.sub(lambda _m: root_dir, script)
    if RE_PROJECT_DIR_WORD.search(p):
        return
    if not is_absolute_path(p):
        p = os.path.normpath(os.path.join(ctx.dir, p))
    rel_script = relative_to(ctx.dir, p).replace('\\', '/')
    body = read_script_body(ctx, rel_script, p)
    if body is None:
        ctx.add(config_finding(rel, 0.9, script, 'HKS04'))
        return
    if RE_ABSOLUTE_PATH.search(script) and not RE_PLUGIN_ROOT_WORD.search(script):
        ctx.add(config_finding(rel, 0.8, script, 'PRT01',
                               message='Hook uses an absolute path; it breaks on other machines'))
    if event in ('Stop', 'SubagentStop') and not RE_STOP_ACTIVE.search(body):
        ctx.add(config_finding(rel_script, 0.7, event, 'HKS03', surface='code'))
    if event in GUARD_EVENTS:
        audit_guard_script(ctx, rel_script, event, body)


def audit_settings(ctx: Ctx, rel: str, text: str) -> None:
    """Review shipped settings: broad permissions, auto-approved MCP, helpers, redirects."""
    try:
        o = parse_json(text)
    except ValueError as exc:
        ctx.add(config_finding(rel, 0.75, str(exc), 'HKS01'))
        return
    perm = get_key(o, 'permissions')

    def flag_setting(evidence: str, confidence: float) -> None:
        """Report a risky shipped setting."""
        ctx.add(config_finding(rel, confidence, evidence, 'HKS13'))

    broad = [x for x in as_list(get_key(perm, 'allow'))
             if RE_BROAD_ALLOW.search(as_text(x).strip()) or RE_BROAD_BASH.search(as_text(x))]
    if broad:
        flag_setting('allow: ' + ', '.join(as_text(x) for x in broad[:5]), 0.85)
    mode = get_key(perm, 'defaultMode') or get_key(o, 'defaultMode')
    if mode and RE_RISKY_MODE.search(as_text(mode)):
        flag_setting('defaultMode: ' + as_text(mode), 0.9)
    enabled = get_key(o, 'enabledMcpjsonServers')
    if get_key(o, 'enableAllProjectMcpServers') is True or (
        isinstance(enabled, (list, str)) and len(enabled) > 0
    ):
        flag_setting('MCP servers approved automatically', 0.85)
    for d in as_list(get_key(perm, 'additionalDirectories')):
        s = as_text(d)
        if RE_TOP_LEVEL_DIR.search(s) and len(
            RE_PATH_SEP.split(RE_TRAILING_SLASHES.sub('', s))
        ) <= 2:
            flag_setting('additionalDirectories reaches a top-level or home folder', 0.8)
            break
    audit_settings_helpers(ctx, rel, o)


def audit_settings_helpers(ctx: Ctx, rel: str, o: Any) -> None:
    """Credential helpers, status line, environment redirects, and hooks of a settings file."""
    for key in (
        'apiKeyHelper', 'awsAuthRefresh', 'awsCredentialExport', 'otelHeadersHelper',
        'gcpAuthRefresh',
    ):
        v = get_key(o, key)
        if v:
            ctx.add(config_finding(rel, 0.85, key + ': ' + as_text(v)[:100], 'HKS14'))
    status_line = get_key(o, 'statusLine')
    if get_key(status_line, 'command'):
        ctx.add(
            config_finding(
                rel, 0.75, 'statusLine runs: ' + as_text(status_line['command'])[:100], 'HKS14',
            )
        )
    for k, v in iter_items(get_key(o, 'env')):
        if RE_ENDPOINT_ENV.search(k):
            shown = '***' if RE_TOKEN_KEY.search(k) else as_text(v)[:60]
            ctx.add(config_finding(
                rel, 0.85, f'env {k}={shown}', 'HKS14',
                message=('Shipped settings redirect the API endpoint, a proxy, or trust roots, '
                         'which can capture every prompt')))
    hooks = get_key(o, 'hooks')
    if hooks:
        audit_hook_events(ctx, rel, hooks)


def audit_mcp(ctx: Ctx, rel: str, text: str) -> None:
    """Review MCP servers: unpinned runners, shell wrappers, plain HTTP, inline secrets, tools."""
    try:
        o = parse_json(text)
    except ValueError as exc:
        ctx.add(config_finding(rel, 0.75, str(exc), 'HKS01'))
        return
    servers = get_key(o, 'mcpServers') or get_key(o, 'servers') or o
    for name, s in iter_items(servers):
        if isinstance(s, dict):
            audit_mcp_server(ctx, rel, name, s)


def audit_mcp_server(ctx: Ctx, rel: str, name: str, s: dict[str, Any]) -> None:
    """Review one MCP server entry."""
    command = s.get('command')
    cmd = as_text(command) if command else ''
    args = [as_text(a) for a in as_list(s.get('args'))]
    full = ' '.join([cmd] + args)
    cmd_base = os.path.basename(cmd)
    if RE_PACKAGE_RUNNER.search(cmd_base):
        pkg = next(
            (a for a in args if not a.startswith('-') and not RE_RUNNER_SUBCOMMAND.search(a)), None,
        )
        if pkg and not RE_PINNED.search(RE_LEADING_AT.sub('', pkg, count=1)):
            ctx.add(config_finding(rel, 0.75, f'{name}: {full[:100]}', 'MCP01'))
    if RE_SHELL_BINARY.search(cmd_base) and any(RE_SHELL_FLAG.search(a) for a in args):
        ctx.add(config_finding(rel, 0.8, f'{name}: {full[:120]}', 'MCP04'))
    url = s.get('url')
    if url:
        u = as_text(url)
        if RE_PLAIN_HTTP_URL.search(u) and not RE_LOCAL_HTTP_URL.search(u):
            ctx.add(config_finding(rel, 0.85, f'{name}: {u}', 'MCP02'))
        elif RE_IP_HTTP_URL.search(u):
            ctx.add(config_finding(rel, 0.7, f'{name}: {u}', 'MCP02'))
    for bag_name in ('env', 'headers'):
        for k, v in iter_items(s.get(bag_name)):
            if looks_like_inline_secret(k, as_text(v)):
                ctx.add(config_finding(rel, 0.85, f'{name}.{k}=***', 'MCP03'))
    audit_mcp_tools(ctx, rel, name, s)


def audit_mcp_tools(ctx: Ctx, rel: str, name: str, s: dict[str, Any]) -> None:
    """Review tool descriptions of an MCP server entry (tool poisoning)."""
    tools = s.get('tools')
    tool_list = tools if isinstance(tools, list) else ([tools] if tools else [])
    for t in tool_list:
        desc = get_key(t, 'description')
        dsc = as_text(desc) if desc else ''
        if len(dsc) > 500:
            ctx.add(config_finding(rel, 0.6, f'{name}: description of {len(dsc)} characters',
                                   'TPO03', severity='medium'))
        if mentions_injection(dsc):
            ctx.add(config_finding(rel, 0.85, dsc[:120], 'TPO01'))


def mentions_injection(text: str) -> bool:
    """True when text trips an injection, refusal-suppression, or leak rule."""
    return any('md' in r['on'] and RE_INJECTION_FAMILY.search(r['id']) and r['re'].search(text)
               for r in LINE_RULES)


def config_finding(
    rel: str, confidence: float, evidence: str, rule_id: str, **extra: Any,
) -> Finding:
    """A finding located in a configuration file."""
    return {'id': rule_id, 'file': rel, 'surface': 'config', 'confidence': confidence,
            'evidence': evidence, **extra}


def audit_hook_events(ctx: Ctx, rel: str, events: Any) -> None:
    """Review the event table of a hooks configuration (event name -> list of matcher groups)."""
    for event, groups in iter_items(events):
        if event == 'description' or not isinstance(groups, (dict, list)):
            continue
        if event not in KNOWN_EVENTS:
            ctx.add(config_finding(rel, 0.8, 'event: ' + event, 'HKS02'))
        for g in as_list(groups):
            if isinstance(g, dict):
                audit_hook_group(ctx, rel, event, g)


def handler_command(h: dict[str, Any]) -> str:
    """The command line of a hook handler: the command followed by its args."""
    command = h.get('command')
    args = ['' if a is None else as_text(a) for a in as_list(h.get('args'))]
    return ' '.join([as_text(command) if command else ''] + args)


def audit_command_handler(ctx: Ctx, rel: str, event: str, h: dict[str, Any], cmd: str) -> None:
    """Checks that apply only to command handlers: timeout, project-dir scripts, network tools."""
    if 'timeout' not in h:
        ctx.add(config_finding(rel, 0.8, cmd[:100], 'HKS06'))
    if RE_PROJECT_DIR_VAR.search(cmd) and RE_SCRIPT_EXT.search(cmd):
        ctx.add(config_finding(rel, 0.7, cmd[:120], 'HKS05'))
    if RE_NET_TOOL_CMD.search(cmd):
        ctx.add(config_finding(rel, 0.8, cmd[:140], 'HKS12'))
    audit_hook_script(ctx, rel, event, cmd)


def read_script_body(ctx: Ctx, rel_script: str, path: str) -> str | None:
    """Text of a hook script: the copy already read, else the file on disk, else None."""
    body = ctx.texts.get(rel_script)
    if body is None and os.path.exists(path):
        try:
            body = read_audited_bytes(path).decode('utf-8', errors='replace')
        except OSError:
            return None
    return body


def audit_guard_script(ctx: Ctx, rel_script: str, event: str, body: str) -> None:
    """A hook on a guard event should be able to block (exit code 2 or a block decision)."""
    if RE_EXIT_2.search(body) or RE_DECISION_BLOCK.search(body):
        return
    if RE_EXIT_1.search(body):
        ctx.add(config_finding(rel_script, 0.7, event + ': exit code 1 does not block', 'HKS07',
                               surface='code'))
    else:
        ctx.add(config_finding(rel_script, 0.5, event + ': no path blocks', 'HKS07', surface='code',
                               severity='low'))


def looks_like_inline_secret(key: str, val: str) -> bool:
    """True for an env or header value that is a literal secret rather than a variable reference."""
    if not val or RE_ENV_REFERENCE.search(val):
        return False
    long_enough = len(val) >= 12 and not RE_BEARER_VAR.search(val)
    named_secret = RE_SECRET_KEY_NAME.search(key) and long_enough
    return bool(RE_SECRET_PREFIX.search(val) or named_secret)
