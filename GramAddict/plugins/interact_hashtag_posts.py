import logging
from functools import partial
from random import seed

import emoji
from colorama.ansi import Fore

from GramAddict.core.decorators import run_safely
from GramAddict.core.handle_sources import handle_posts
from GramAddict.core.interaction import (
    interact_with_user,
    is_follow_limit_reached_for_source,
)
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.utils import get_value, init_on_things, sample_sources

logger = logging.getLogger(__name__)
seed()


class InteractHashtagPosts(Plugin):
    """Handles the functionality of interacting with hashtag post owners"""

    def _init_(self):
        super()._init_()
        self.description = "Handles the functionality of interacting with hashtag post owners"
        self.arguments = [
            {
                "arg": "--hashtag-posts",
                "nargs": "+",
                "help": "Interact with post owners from specified hashtags",
                "metavar": ("hashtag1", "hashtag2"),
                "default": None,
                "operation": True,
            }
        ]

    def run(self, device, configs, storage, sessions, profile_filter, plugin):
        class State:
            def _init_(self):
                self.is_job_completed = False

        self.device_id = configs.args.device
        self.sessions = sessions
        self.session_state = sessions[-1]
        self.args = configs.args
        self.current_mode = plugin

        sources = sample_sources(self.args.hashtag_posts, self.args.truncate_sources)

        for source in sources:
            (
                active_limits_reached,
                _,
                actions_limit_reached,
            ) = self.session_state.check_limit(limit_type=self.session_state.Limit.ALL)

            if active_limits_reached or actions_limit_reached:
                logger.info("Session limits reached.")
                self.session_state.check_limit(
                    limit_type=self.session_state.Limit.ALL, output=True
                )
                break

            self.state = State()
            if not source.startswith("#"):
                source = "#" + source

            logger.info(
                f"Handle {emoji.emojize(source, use_aliases=True)}",
                extra={"color": f"{Fore.BLUE}"},
            )

            (
                on_interaction,
                stories_percentage,
                likes_percentage,
                follow_percentage,
                comment_percentage,
                pm_percentage,
                interact_percentage,
            ) = init_on_things(source, self.args, self.sessions, self.session_state)

            @run_safely(
                device=device,
                device_id=self.device_id,
                sessions=self.sessions,
                session_state=self.session_state,
                screen_record=self.args.screen_record,
                configs=configs,
            )
            def job():
                self.handle_hashtag(
                    device,
                    source,
                    storage,
                    profile_filter,
                    on_interaction,
                    stories_percentage,
                    likes_percentage,
                    follow_percentage,
                    comment_percentage,
                    pm_percentage,
                    interact_percentage,
                )
                self.state.is_job_completed = True

            while not self.state.is_job_completed:
                job()

    def handle_hashtag(
        self,
        device,
        hashtag,
        storage,
        profile_filter,
        on_interaction,
        stories_percentage,
        likes_percentage,
        follow_percentage,
        comment_percentage,
        pm_percentage,
        interact_percentage,
    ):
        interaction = partial(
            interact_with_user,
            my_username=self.session_state.my_username,
            likes_count=self.args.likes_count,
            likes_percentage=likes_percentage,
            stories_percentage=stories_percentage,
            follow_percentage=follow_percentage,
            comment_percentage=comment_percentage,
            pm_percentage=pm_percentage,
            profile_filter=profile_filter,
            args=self.args,
            session_state=self.session_state,
            scraping_file=self.args.scrape_to_file,
            current_mode=self.current_mode,
        )

        follow_limit = get_value(self.args.follow_limit, None, 15)
        is_follow_limit_reached = partial(
            is_follow_limit_reached_for_source,
            session_state=self.session_state,
            follow_limit=follow_limit,
            source=hashtag,
        )

        handle_posts(
            device=device,
            username=self.session_state.my_username,
            sessions=self.sessions,
            likes_limit=self.args.total_likes_limit,
            on_interaction=on_interaction,
            my_username=self.session_state.my_username,
            is_likers=False,  # This is hashtag mode, not liker mode
        )