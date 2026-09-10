# System Analyzer Current

The extracted theme for the existing light System Analyzer interface. This is
documentation of the shipped baseline, not a redesign. The executable source
of truth remains `maintenance/ui/styles.py`.

## Palette

| token | hex | role |
|---|---|---|
| `base` | `#F4F7FB` | page background |
| `surface` | `#FFFFFF` | cards, dialogs, controls |
| `line` | `#E4E7EC` | borders and dividers |
| `ink` | `#172033` | primary text |
| `ink-2` | `#667085` | secondary text |
| `ink-3` | `#98A2B3` | disabled and metadata only |
| `accent` | `#4F46E5` | actions, focus, active indicators |
| `accent-ink` | `#FFFFFF` | text on accent fills |

## Semantic Colors

`success` is `#16803C`, `warning` is `#B45309`, and `danger` is `#B42318`.
They remain independent of the user-selectable accent.

```contrast
ink        on base    AAA
ink-2      on base    AA
accent-ink on accent  AA
accent     on base    UI
```

`ink-3` is deliberately restricted to disabled/meta presentation and is not a
body-text token.
