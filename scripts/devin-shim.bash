# devin-delegate shell shim — intercept raw devin calls at the shell level
# Source this in your .bashrc or .zshrc: source "$HOME/.local/share/devin-delegate-shim.sh"

# Fallback: if devin-delegate binary is broken, use direct path
_DD_DELEGATE_SCRIPT="${DEVIN_DELEGATE_SCRIPT:-$HOME/.agents/skills/devin-delegate/scripts/delegate.py}"

_devin_delegate_extract_task() {
  local -a args=("$@")
  local i arg next

  for ((i=0; i<${#args[@]}; i++)); do
    arg="${args[$i]}"
    if [[ "$arg" == "--print" || "$arg" == "--task" ]]; then
      if (( i + 1 < ${#args[@]} )); then
        next="${args[$((i+1))]}"
        printf '%s' "$next"
        return 0
      fi
    fi
    if [[ "$arg" == --print=* || "$arg" == --task=* ]]; then
      printf '%s' "${arg#*=}"
      return 0
    fi
  done

  # Fall back to last non-flag positional.
  for ((i=${#args[@]}-1; i>=0; i--)); do
    arg="${args[$i]}"
    if [[ "$arg" != -* ]]; then
      printf '%s' "$arg"
      return 0
    fi
  done

  return 1
}

_devin_delegate_extract_workspace() {
  local -a args=("$@")
  local i arg

  for ((i=0; i<${#args[@]}; i++)); do
    arg="${args[$i]}"
    if [[ "$arg" == "--workspace" && $((i + 1)) -lt ${#args[@]} ]]; then
      printf '%s' "${args[$((i+1))]}"
      return 0
    fi
    if [[ "$arg" == --workspace=* ]]; then
      printf '%s' "${arg#*=}"
      return 0
    fi
  done

  return 1
}

devin() {
  # Recursion guard: if we're already inside the wrapper, forward to real devin
  if [[ -n "${DEVIN_DELEGATE_ACTIVE:-}" ]]; then
    command devin "$@"
    return $?
  fi

  if [[ "${DEVIN_DELEGATE_NO_SHIM:-}" == "1" ]]; then
    command devin "$@"
    return
  fi

  local joined=" $* "
  if [[ "$joined" != *" --print "* && "$joined" != *" --task "* && "$joined" != *"--print="* && "$joined" != *"--task="* ]]; then
    command devin "$@"
    return
  fi

  local task
  if ! task="$(_devin_delegate_extract_task "$@")" || [[ -z "$task" ]]; then
    command devin "$@"
    return
  fi

  local workspace
  workspace="$(_devin_delegate_extract_workspace "$@")" || true

  echo "[devin-delegate] Intercepted raw devin call -> routing through wrapper" >&2

  # Build delegate command
  local delegate_cmd="devin-delegate --task \"$task\""
  if [[ -n "$workspace" ]]; then
    delegate_cmd="$delegate_cmd --workspace \"$workspace\""
  fi

  if command -v devin-delegate >/dev/null 2>&1; then
    eval "$delegate_cmd"
    return $?
  else
    # Fallback to direct script invocation
    echo "[devin-delegate] CLI not found, using direct script path" >&2
    python3 "$_DD_DELEGATE_SCRIPT" --task "$task" ${workspace:+--workspace "$workspace"}
    return $?
  fi
}
