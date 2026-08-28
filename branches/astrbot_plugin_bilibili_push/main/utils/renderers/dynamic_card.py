from pathlib import Path

from .movie_card import MovieCardTheme


class DynamicCardTheme(MovieCardTheme):
    def __init__(
        self,
        renderer,
        template_name="dynamic_movie_card.html.jinja",
        display_timezone="Asia/Shanghai",
        avatar_cache_dir: Path | None = None,
    ):
        super().__init__(
            renderer,
            template_name=template_name,
            display_timezone=display_timezone,
            avatar_cache_dir=avatar_cache_dir,
        )
