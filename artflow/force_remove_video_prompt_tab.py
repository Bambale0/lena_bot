from pathlib import Path
import re

TARGETS = []
for root in ["webapp/src", "webapp/dist/assets"]:
    rp = Path(root)
    if rp.exists():
        TARGETS += [p for p in rp.rglob("*") if p.suffix in {".js", ".jsx", ".ts", ".tsx"}]

for p in TARGETS:
    s = p.read_text(encoding="utf-8")
    old = s

    # Убираем самые частые массивы табов.
    replacements = {
        '["all","photo","video"]': '["all","photo"]',
        "['all','photo','video']": "['all','photo']",
        '["Все","Фото","Видео"]': '["Все","Фото"]',
        "['Все','Фото','Видео']": "['Все','Фото']",
        '["Все", "Фото", "Видео"]': '["Все", "Фото"]',
        "['Все', 'Фото', 'Видео']": "['Все', 'Фото']",
        '["all","image","video"]': '["all","image"]',
        '["Все","Изображения","Видео"]': '["Все","Изображения"]',
    }
    for a, b in replacements.items():
        s = s.replace(a, b)

    # Убираем object/tab definitions.
    s = re.sub(r'\{\s*id\s*:\s*["\']video["\']\s*,\s*label\s*:\s*["\']Видео["\']\s*\}\s*,?', "", s)
    s = re.sub(r'\{\s*key\s*:\s*["\']video["\']\s*,\s*label\s*:\s*["\']Видео["\']\s*\}\s*,?', "", s)
    s = re.sub(r'\{\s*value\s*:\s*["\']video["\']\s*,\s*label\s*:\s*["\']Видео["\']\s*\}\s*,?', "", s)

    # Для минифицированного dist часто бывает без пробелов:
    s = s.replace('{id:"video",label:"Видео"},', "")
    s = s.replace('{key:"video",label:"Видео"},', "")
    s = s.replace('{value:"video",label:"Видео"},', "")
    s = s.replace(',{id:"video",label:"Видео"}', "")
    s = s.replace(',{key:"video",label:"Видео"}', "")
    s = s.replace(',{value:"video",label:"Видео"}', "")

    # Если где-то категория строится простым массивом объектов с title.
    s = s.replace('{id:"video",title:"Видео"},', "")
    s = s.replace(',{id:"video",title:"Видео"}', "")

    # Не трогаем кнопку Студия -> Видео:
    # поэтому НЕ удаляем весь текст "Видео", только фильтры prompt-library.

    if s != old:
        p.write_text(s, encoding="utf-8")
        print("patched", p)

print("done")
