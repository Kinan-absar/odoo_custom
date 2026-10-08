"""Locate printed signer headings in PO pages, using PDF text coordinates."""
import io
import re


def normalize(text):
    return ''.join(char.lower() for char in text if char.isalnum())


def aliases(role_name):
    key = normalize(role_name)
    if key in ('projectdirector', 'projectsdirector'):
        return ('Projects Director', 'Project Director')
    if key in ('ceo', 'chiefexecutiveofficer'):
        return ('Chief Executive Officer', 'CEO')
    return (role_name.strip(),)


def locate_signature_anchors(pdf_content, po_page_count, roles):
    """Return normalized Sign positions keyed by workflow step ID.

    Only inspect PO pages, excluding quotation/MR attachments. Match individual
    glyph bounds so two headings on a shared text line retain separate positions.
    Reject missing/ambiguous headings rather than placing a wrong signer's box.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTTextLine

    found = {str(key): {label: [] for label in aliases(name)}
             for key, name in roles.items()}
    patterns = {label: re.compile(
        r'(?<!\w)' + r'\s+'.join(re.escape(word) for word in label.split()) + r'(?!\w)',
        re.IGNORECASE,
    ) for labels in found.values() for label in labels}

    def text_lines(item):
        if isinstance(item, LTTextLine):
            yield item
        elif hasattr(item, '__iter__'):
            for child in item:
                yield from text_lines(child)

    for page_index, layout in enumerate(extract_pages(
            io.BytesIO(pdf_content), page_numbers=range(po_page_count))):
        for line in text_lines(layout):
            text, lookup = '', []
            for item in line:
                if not hasattr(item, 'get_text'):
                    continue
                for char in item.get_text():
                    text += char
                    lookup.append(item if isinstance(item, LTChar) else None)
            for key, role_name in roles.items():
                for label in aliases(role_name):
                    for match in patterns[label].finditer(text):
                        matched = [glyph for glyph in lookup[match.start():match.end()]
                                   if glyph is not None]
                        if not matched:
                            continue
                        x0 = min(g.x0 for g in matched)
                        x1 = max(g.x1 for g in matched)
                        bottom = min(g.y0 for g in matched)
                        # Center the field under the actual printed heading.
                        x = max(0.02, min(0.72, (x0 + x1) / (2 * layout.width) - 0.13))
                        y = (layout.y1 - bottom) / layout.height + 0.012
                        anchor = {'page': page_index + 1, 'posX': x, 'posY': y}
                        matches = found[str(key)][label]
                        if anchor not in matches:
                            matches.append(anchor)
    result = {}
    for key, role_name in roles.items():
        # Prefer the full printed role title over its acronym elsewhere in the PO.
        matches = next((found[str(key)][label] for label in aliases(role_name)
                        if found[str(key)][label]), [])
        if len(matches) != 1:
            raise ValueError("Signer heading '%s': expected one match in the PO, found %s. "
                             "Check the printed role heading before preparing Sign." % (role_name, len(matches)))
        anchor = matches[0]
        if anchor['posY'] + 0.053 > 0.97:
            raise ValueError("There is not enough space below signer heading '%s' for signature and date." % role_name)
        result[str(key)] = anchor
    return result
