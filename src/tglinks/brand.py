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

ICON_LINK = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'

NAME = "cool stuff"
