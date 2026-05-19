# devin-delegate shell shim
# Intercepts direct `devin --print/--task` calls and routes through devin-delegate.
# Source from shell rc; no effect for non-interactive processes.

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

devin() {
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

  echo "[devin-delegate] intercepted raw devin call -> routing through wrapper" >&2
  command devin-delegate --task="$task"
}
