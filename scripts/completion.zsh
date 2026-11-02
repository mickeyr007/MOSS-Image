# Complete MOSS-Image commands for `make <Tab>` in the repository root.
typeset -g _moss_image_root=${${(%):-%x}:A:h:h}

_moss_image_make_completion() {
  if [[ ${PWD:A} != $_moss_image_root || $CURRENT -ne 2 || $words[CURRENT] == -* ]]; then
    _make
    return
  fi

  local -a targets
  targets=(${(f)"$(awk '/^\.PHONY:/ { for (i = 2; i <= NF; i++) print $i }' "$_moss_image_root/Makefile")"})
  compadd -- "${targets[@]}"
}

compdef _moss_image_make_completion make
