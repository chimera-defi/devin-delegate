# Shell completion for devin-delegate
# Source this in your shell rc: source "$HOME/.local/share/devin-delegate-completion.bash"

_devin_delegate_completions() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="--task --context-file --task-class --dry-run --print-envelope --check --subagent-check --stats --interactive -i --batch --last --quick -q --cost --template --templates --suggest --history --retry --timeout-override --health --safety-check --workspace --help"

    case "$prev" in
        --task-class)
            COMPREPLY=( $(compgen -W "research implement debug review browser" -- "$cur") )
            return 0
            ;;
        --context-file|--batch|--workspace)
            COMPREPLY=( $(compgen -f -- "$cur") )
            return 0
            ;;
    esac
    COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
}

complete -F _devin_delegate_completions devin-delegate
complete -F _devin_delegate_completions dd