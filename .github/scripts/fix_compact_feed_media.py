from pathlib import Path

root = Path(__file__).resolve().parents[2]
main_path = root / "artflow/webapp/src/main.jsx"
style_path = root / "artflow/webapp/src/style.css"

main = main_path.read_text(encoding="utf-8")
main = main.replace(
    '  const mediaType = String(item.gen_type || item.type || item.generation_type || "").toLowerCase().includes("video") ? "video" : "image";\n',
    '',
    1,
)
main = main.replace(
    '            type={mediaType}\n',
    '            type={/\\.(mp4|webm|mov)(?:$|\\?)/i.test(url) ? "video" : "image"}\n',
    1,
)
main_path.write_text(main, encoding="utf-8")

style = style_path.read_text(encoding="utf-8")
style = style.replace('.feedCompactMedia video{pointer-events:none}\n', '', 1)
style_path.write_text(style, encoding="utf-8")

print("compact feed media handling fixed")
