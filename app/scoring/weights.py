"""
Category weights from SCORING.md:
Overall % = On-site x 0.26 + Indexing x 0.12 + Linking/Social x 0.62
"""
CATEGORY_WEIGHTS = {
    "on_site": 0.26,
    "indexing": 0.12,
    "linking_social": 0.62,
}

# Elements per category (used for report grouping)
ELEMENTS = {
    "on_site": [
        "keyword_focus",
        "url_structure",
        "title_tags",
        "meta_descriptions",
        "heading_tags",
        "content",
        "internal_linking",
        "image_alts",
        "nofollow",
        "page_load_speed",
        "schema",
        "ai_optimization",
        "code_validation",
    ],
    "indexing": [
        "indexing_optimization",
        "page_exclusions",
        "page_inclusions",
        "url_redirects",
        "duplicate_content",
        "broken_links",
    ],
    "linking_social": [
        "linking_root_domains",
        "inbound_followed_links",
        "authority_trust",
        "social_media",
        "competitive_link_comparison",
        "nap",
    ],
}
