"""The mark: two overlapping frames, one link laid over another.

Kept in one place because it appears in three: the tab icon, the header of the
search page and the header of the sign-in pages. Monochrome on purpose — the
whole site has no accent colour.
"""

# a square background rather than a transparent one: the tab strip can be light
# or dark and the frames only read against the site's own black
FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="7" fill="#0b0b0c"/>'
    '<rect x="6.5" y="6.5" width="13" height="13" fill="none" '
    'stroke="#ededf0" stroke-width="2"/>'
    '<rect x="12.5" y="12.5" width="13" height="13" fill="none" '
    'stroke="#ededf0" stroke-width="2"/>'
    "</svg>"
)

# inherits the text colour of whatever line it sits on
GLYPH = (
    '<svg class="glyph" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">'
    '<rect x="3.4" y="3.4" width="11.2" height="11.2" fill="none" '
    'stroke="currentColor" stroke-width="1.7"/>'
    '<rect x="9.4" y="9.4" width="11.2" height="11.2" fill="none" '
    'stroke="currentColor" stroke-width="1.7"/>'
    "</svg>"
)

# the little control on a card that only the admin is shown: an eye with a
# stroke through it. drawn rather than typed, because an emoji in a source file
# is a character whose font, size and colour belong to the reader's system
HIDE_ICON = (
    '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" '
    'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">'
    '<path d="M2.6 12S6.4 5.9 12 5.9c1.5 0 2.8.4 4 1"/>'
    '<path d="M19.3 8.4c1.3 1.3 2.1 2.7 2.1 3.6 0 0-3.8 6.1-9.4 6.1-1.7 0-3.2-.5-4.5-1.3"/>'
    '<path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>'
    '<path d="M4 20 20 4"/>'
    "</svg>"
)

ICON_LINK = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'

NAME = "cool stuff"
