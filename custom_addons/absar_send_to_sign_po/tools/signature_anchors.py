"""Locate printed signer headings in PO pages, using PDF text coordinates."""
import io


def normalize(text):
    return ''.join(char.lower() for char in text if char.isalnum())


def aliases(role_name):
    key = normalize(role_name)
    if key in ('projectdirector', 'projectsdirector'):
        return ('projectdirector', 'projectsdirector')
    if key in ('ceo', 'chiefexecutiveofficer'):
        return ('chiefexecutiveofficer', 'ceo')
    return (key,)


def locate_signature_anchors(pdf_content, po_page_count, roles):
    """Return normalized Sign positions keyed by workflow step ID.

    Only inspect PO pages, excluding quotation/MR attachments. Match individual
    glyph bounds so two headings on a shared text line retain separate positions.
    Reject missing/ambiguous headings rather than placing a wrong signer's box.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTTextLine

    found = {str(key): [] for key in roles}

    def text_lines(item):
        if isinstance(item, LTTextLine):
            yield item
        elif hasattr(item, '__iter__'):
            for child in item:
                yield from text_lines(child)

    for page_index, layout in enumerate(extract_pages(
            io.BytesIO(pdf_content), page_numbers=range(po_page_count))):
        for line in text_lines(layout):
            glyphs = [char for char in line if isinstance(char, LTChar)]
            text, lookup = '', []
            for glyph in glyphs:
                for char in glyph.get_text():
                    if char.isalnum():
                        text += char.lower()
                        lookup.append(glyph)
            for key, role_name in roles.items():
                for label in aliases(role_name):
                    start = 0
                    while label:
                        offset = text.find(label, start)
                        if offset < 0:
                            break
                        matched = lookup[offset:offset + len(label)]
                        x0 = min(g.x0 for g in matched)
                        x1 = max(g.x1 for g in matched)
                        bottom = min(g.y0 for g in matched)
                        # Center the field under the actual printed heading.
                        x = max(0.02, min(0.72, (x0 + x1) / (2 * layout.width) - 0.13))
                        y = (layout.y1 - bottom) / layout.height + 0.012
                        anchor = {'page': page_index + 1, 'posX': x, 'posY': y}
                        if anchor not in found[str(key)]:
                            found[str(key)].append(anchor)
                        start = offset + len(label)
    result = {}
    for key, role_name in roles.items():
        matches = found[str(key)]
        if len(matches) != 1:
            raise ValueError("Signer heading '%s': expected one match in the PO, found %s. "
                             "Check the printed role heading before preparing Sign." % (role_name, len(matches)))
        anchor = matches[0]
        if anchor['posY'] + 0.053 > 0.97:
            raise ValueError("There is not enough space below signer heading '%s' for signature and date." % role_name)
        result[str(key)] = anchor
    return result
