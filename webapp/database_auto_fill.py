from __future__ import annotations


AUTO_PHASE_QUERY_PARAM = "db_auto_phase"


def normalize_auto_phase(value: str | None) -> str:
    return "run" if value == "run" else "display"


def next_auto_phase(current_phase: str) -> str:
    return "run" if normalize_auto_phase(current_phase) != "run" else "display"


def build_auto_reload_script(delay_seconds: int, next_phase_value: str) -> str:
    safe_delay_ms = max(int(delay_seconds), 1) * 1000
    safe_next_phase = normalize_auto_phase(next_phase_value)
    return f"""
        <script>
        const delayMs = {safe_delay_ms};
        const nextPhase = {safe_next_phase!r};
        const phaseQueryParam = {AUTO_PHASE_QUERY_PARAM!r};

        function navigateForAutoFill() {{
          const candidateWindows = [window.parent, window.top, window];
          for (const candidate of candidateWindows) {{
            if (!candidate) {{
              continue;
            }}
            try {{
              const target = new URL(candidate.location.href);
              target.searchParams.set(phaseQueryParam, nextPhase);
              const targetHref = target.toString();
              if (candidate.location.href === targetHref) {{
                candidate.location.reload();
              }} else {{
                candidate.location.assign(targetHref);
              }}
              return;
            }} catch (error) {{
              // Keep trying fallbacks until one can navigate the app shell.
            }}
          }}
        }}

        setTimeout(() => {{
          navigateForAutoFill();
        }}, delayMs);
        </script>
    """
