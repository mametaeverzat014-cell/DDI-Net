# external/

Сюда кладутся авторские реализации baseline-моделей из литературы. Они
**адаптируются под наши схемы разбиения, а не переписываются с нуля** —
переписанная с нуля модель сравнивает не опубликованный метод, а нашу
интерпретацию опубликованного метода.

| Репозиторий | Статья | Статус |
|---|---|---|
| `SSI-DDI/` | Nyamabo AK, Yu H, Shi J-Y. SSI-DDI: substructure-substructure interactions for drug-drug interaction prediction. Brief Bioinform, 2021. | **не клонирован** |
| `MHCADDI/` | Deac A, Huang Y-H, Veličković P, Liò P, Tang J. Drug-Drug Adverse Effect Prediction with Graph Co-Attention. arXiv:1905.00534, 2019. | **не клонирован** |

`github.com` из рабочего окружения недоступен (HTTP 403 от egress-прокси),
поэтому репозитории клонируются вручную.

При клонировании записать в `DATA_PROVENANCE.md`: URL, **хеш коммита**, дату,
лицензию. Без хеша коммита сравнение невоспроизводимо — авторский код меняется.

Содержимое подкаталогов не коммитится (см. `.gitignore`).
