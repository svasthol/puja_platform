"""Compare en vs te catalogue names via live API (i18n QA)."""
from __future__ import annotations

import httpx
from qa_client import BASE, auth_headers, login


def _is_te(s: str) -> bool:
    return any("\u0c00" <= ch <= "\u0c7f" for ch in (s or ""))


def main() -> None:
    token = login("+919000000111", "customer")
    h = auth_headers(token)
    lines: list[str] = []
    with httpx.Client(base_url=BASE, timeout=20.0) as c:
        out = {}
        cats = {}
        for loc in ("en", "te"):
            r = c.get(f"/v1/pujas?locale={loc}&limit=12", headers=h)
            r.raise_for_status()
            data = r.json()
            out[loc] = [(p.get("name"), p.get("slug")) for p in data.get("pujas", [])]
            cats[loc] = [ct.get("name") for ct in data.get("categories", [])]

    lines.append("idx | slug | EN name | TE name | te_has_telugu | en_has_telugu | te_empty")
    for i, (en, te) in enumerate(zip(out["en"], out["te"])):
        te_empty = (te[0] or "") == ""
        lines.append(
            f"{i} | {en[1]} | {en[0]!r} | {te[0]!r} | {_is_te(te[0])} | {_is_te(en[0])} | {te_empty}"
        )
    lines.append("\n-- categories EN --")
    lines.append(repr(cats["en"]))
    lines.append("-- categories TE --")
    lines.append(repr(cats["te"]))

    with open("i18n_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote i18n_result.txt")


if __name__ == "__main__":
    main()
