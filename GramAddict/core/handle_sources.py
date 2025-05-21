import logging
import os
import time
from functools import partial
from os import path

from atomicwrites import atomic_write
from colorama import Fore

from GramAddict.core.device_facade import Direction, Timeout
from GramAddict.core.navigation import (
    nav_to_blogger,
    nav_to_feed,
    nav_to_hashtag_or_place,
    nav_to_post_likers,
)
from GramAddict.core.resources import ClassName
from GramAddict.core.storage import FollowingStatus
from GramAddict.core.utils import (
    get_value,
    inspect_current_view,
    random_choice,
    random_sleep,
)
from GramAddict.core.views import (
    FollowingView,
    LikeMode,
    OpenedPostView,
    Owner,
    PostsViewList,
    ProfileView,
    SwipeTo,
    TabBarView,
    UniversalActions,
    case_insensitive_re,
)

logger = logging.getLogger(__name__)


def interact(
    storage,
    is_follow_limit_reached,
    username,
    interaction,
    device,
    session_state,
    current_job,
    target,
    on_interaction,
):
    can_follow = False
    if is_follow_limit_reached is not None:
        can_follow = not is_follow_limit_reached() and storage.get_following_status(
            username
        ) in [FollowingStatus.NONE, FollowingStatus.NOT_IN_LIST]

    (
        interaction_succeed,
        followed,
        requested,
        scraped,
        pm_sent,
        number_of_liked,
        number_of_watched,
        number_of_comments,
    ) = interaction(device, username=username, can_follow=can_follow)

    add_interacted_user = partial(
        storage.add_interacted_user,
        session_id=session_state.id,
        job_name=current_job,
        target=target,
    )

    add_interacted_user(
        username,
        followed=followed,
        is_requested=requested,
        scraped=scraped,
        liked=number_of_liked,
        watched=number_of_watched,
        commented=number_of_comments,
        pm_sent=pm_sent,
    )
    return on_interaction(
        succeed=interaction_succeed,
        followed=followed,
        scraped=scraped,
    )



def handle_blogger(
    self,
    device,
    session_state,
    blogger,
    current_job,
    storage,
    profile_filter,
    on_interaction,
    interaction,
    is_follow_limit_reached,
):
    if not nav_to_blogger(device, blogger, session_state.my_username):
        return
    can_interact = False
    if storage.is_user_in_blacklist(blogger):
        logger.info(f"@{blogger} is in blacklist. Skip.")
    else:
        interacted, interacted_when = storage.check_user_was_interacted(blogger)
        if interacted:
            can_reinteract = storage.can_be_reinteract(
                interacted_when, get_value(self.args.can_reinteract_after, None, 0)
            )
            logger.info(
                f"@{blogger}: already interacted on {interacted_when:%Y/%m/%d %H:%M:%S}. {'Interacting again now' if can_reinteract else 'Skip'}."
            )
            if can_reinteract:
                can_interact = True
        else:
            can_interact = True

    if can_interact:
        logger.info(
            f"@{blogger}: interact",
            extra={"color": f"{Fore.YELLOW}"},
        )
        if not interact(
            storage=storage,
            is_follow_limit_reached=is_follow_limit_reached,
            username=blogger,
            interaction=interaction,
            device=device,
            session_state=session_state,
            current_job=current_job,
            target=blogger,
            on_interaction=on_interaction,
        ):
            return


def handle_blogger_from_file(
    self,
    device,
    parameter_passed,
    current_job,
    storage,
    on_interaction,
    interaction,
    is_follow_limit_reached,
):
    need_to_refresh = True
    on_following_list = False
    limit_reached = False

    filename: str = os.path.join(storage.account_path, parameter_passed.split(" ")[0])
    try:
        amount_of_users = get_value(parameter_passed.split(" ")[1], None, 10)
    except IndexError:
        amount_of_users = 10
        logger.warning(
            f"You didn't passed how many users should be processed from the list! Default is {amount_of_users} users."
        )
    if path.isfile(filename):
        with open(filename, "r", encoding="utf-8") as f:
            usernames = [line.replace(" ", "") for line in f if line != "\n"]
        len_usernames = len(usernames)
        if len_usernames < amount_of_users:
            amount_of_users = len_usernames
        logger.info(
            f"In {filename} there are {len_usernames} entries, {amount_of_users} users will be processed."
        )
        not_found = []
        processed_users = 0
        try:
            for line, username_raw in enumerate(usernames, start=1):
                username = username_raw.strip()
                can_interact = False
                if current_job == "unfollow-from-file":
                    unfollowed = do_unfollow_from_list(
                        device, username, on_following_list
                    )
                    on_following_list = True
                    if unfollowed:
                        storage.add_interacted_user(
                            username, self.session_state.id, unfollowed=True
                        )
                        self.session_state.totalUnfollowed += 1
                        limit_reached = self.session_state.check_limit(
                            limit_type=self.session_state.Limit.UNFOLLOWS
                        )
                        processed_users += 1
                    else:
                        not_found.append(username_raw)
                    if limit_reached:
                        logger.info("Unfollows limit reached.")
                        break
                    if processed_users == amount_of_users:
                        logger.info(
                            f"{processed_users} users have been unfollowed, going to the next job."
                        )
                        break
                else:
                    if storage.is_user_in_blacklist(username):
                        logger.info(f"@{username} is in blacklist. Skip.")
                    else:
                        (
                            interacted,
                            interacted_when,
                        ) = storage.check_user_was_interacted(username)
                        if interacted:
                            can_reinteract = storage.can_be_reinteract(
                                interacted_when,
                                get_value(self.args.can_reinteract_after, None, 0),
                            )
                            logger.info(
                                f"@{username}: already interacted on {interacted_when:%Y/%m/%d %H:%M:%S}. {'Interacting again now' if can_reinteract else 'Skip'}."
                            )
                            if can_reinteract:
                                can_interact = True
                        else:
                            can_interact = True

                    if not can_interact:
                        continue
                    if need_to_refresh:
                        search_view = TabBarView(device).navigateToSearch()
                    profile_view = search_view.navigate_to_target(username, current_job)
                    need_to_refresh = False
                    if not profile_view:
                        not_found.append(username_raw)
                        continue

                    if not interact(
                        storage=storage,
                        is_follow_limit_reached=is_follow_limit_reached,
                        username=username,
                        interaction=interaction,
                        device=device,
                        session_state=self.session_state,
                        current_job=current_job,
                        target=username,
                        on_interaction=on_interaction,
                    ):
                        return
                    device.back()
                    processed_users += 1
                    if processed_users == amount_of_users:
                        logger.info(
                            f"{processed_users} users have been interracted, going to the next job."
                        )
                        return
        finally:
            if not_found:
                with open(
                    f"{os.path.splitext(filename)[0]}_not_found.txt",
                    mode="a+",
                    encoding="utf-8",
                ) as f:
                    f.writelines(not_found)
            if self.args.delete_interacted_users and len_usernames != 0:
                with atomic_write(filename, overwrite=True, encoding="utf-8") as f:
                    f.writelines(usernames[line:])
    else:
        logger.warning(
            f"File {filename} not found. You have to specify the right relative path from this point: {os.getcwd()}"
        )
        return

    logger.info(f"Interact with users in {filename} completed.")
    device.back()


def do_unfollow_from_list(device, username, on_following_list):
    if not on_following_list:
        ProfileView(device).click_on_avatar()
        if ProfileView(device).navigateToFollowing() and UniversalActions(
            device
        ).search_text(username):
            return FollowingView(device).do_unfollow_from_list(username)
    else:
        if username is not None:
            UniversalActions(device).search_text(username)
        return FollowingView(device).do_unfollow_from_list(username)

def open_hashtag(session_state, hashtag):
    """
    Navigates to the hashtag search page.
    Returns True if successful, False otherwise.
    """
    try:
        search_view = TabBarView(session_state.device).navigateToSearch()
        result = search_view.navigate_to_hashtag_or_place(f"#{hashtag}")
        return result is not None
    except Exception as e:
        logger.warning(f"Failed to open hashtag #{hashtag}: {e}")
        return False


def open_first_post(device):
    """
    Opens the first post in a hashtag feed.
    Returns True if successful, False otherwise.
    """
    posts_view = PostsViewList(device)
    first_post = posts_view.get_first_post()
    if first_post and first_post.click_retry():
        return True
    return False


def scroll_and_collect_likers(device, plugin_state, max_likers=30):
    """
    Opens the post likers list and scrolls to collect usernames.
    """
    try:
        post_view = OpenedPostView(device)
        if not post_view.open_likers():
            return []

        nav_to_post_likers(device)

        user_list = device.find(resourceIdMatches=".*user_list_container.*")
        row_height, _ = inspect_current_view(user_list)

        likers = set()
        scrolls = 0

        while len(likers) < max_likers and scrolls < 5:
            for item in user_list:
                if item.get_height() < row_height:
                    continue
                username_view = item.child(index=1).child(index=0).child()
                if username_view.exists():
                    liker = username_view.get_text()
                    likers.add(liker)

            user_list.scroll(Direction.DOWN)
            scrolls += 1

        return list(likers)
    except Exception as e:
        logger.warning(f"Failed to collect likers: {e}")
        return []

def swipe_to_next_post(device):
    """
    Swipes to the next post in the hashtag feed.
    Returns True if the swipe was successful.
    """
    try:
        device.swipe((800, 1500), (200, 1500), 20)  # Swipe left
        time.sleep(2)  # Wait briefly for UI to update
        return True
    except Exception as e:
        logger.warning(f"Swipe to next post failed: {e}")
        return False

def wait_for_post_to_load(device, timeout=10):
    """
    Waits for post content to load.
    Returns True if post is loaded, False otherwise.
    """
    try:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if device.find(resourceIdMatches=".*like_button.*").exists():
                return True
            time.sleep(0.5)
        return False
    except Exception as e:
        logger.warning(f"Error waiting for post to load: {e}")
        return False

def get_post_owner_username(device):
    """
    Gets the username of the post owner.
    """
    try:
        username_view = device.find(resourceIdMatches=".*user_name_text_view.*")
        if username_view.exists():
            return username_view.get_text()
        return None
    except Exception as e:
        logger.warning(f"Failed to get post owner's username: {e}")
        return None

def interact_with_user(device, username, plugin_state):
    """
    Interacts with the user: like, follow, etc.
    """
    try:
        logger.info(f"Interacting with @{username}")

        # Like the post
        like_button = device.find(resourceIdMatches=".*like_button.*")
        if like_button.exists() and not like_button.get_selected():
            like_button.click()
            time.sleep(1)
            logger.info("Post liked")

        # Follow the user (if plugin_state wants it)
        if plugin_state.get("follow", False):
            follow_button = device.find(textMatches="Follow|Follow Back")
            if follow_button.exists():
                follow_button.click()
                logger.info("User followed")

        return True
    except Exception as e:
        logger.warning(f"Failed to interact with user @{username}: {e}")
        return False



def handle_likers(session_state, plugin_state):
    quota_supervisor = plugin_state.quota_supervisor
    logger = plugin_state.logger
    args = plugin_state.args
    device = session_state.device
    state = plugin_state.state

    interactions_limit_reached = quota_supervisor.live_check("interactions") <= 0
    if interactions_limit_reached:
        logger.info("Interaction quota reached, skipping liker interactions.")
        return

    for hashtag in plugin_state.input_hashtags:
        logger.info(f"Processing hashtag: {hashtag}")
        opened = open_hashtag(session_state, hashtag)
        if not opened:
            logger.warning(f"Couldn't open hashtag #{hashtag}")
            continue

        if not open_first_post(device):
            logger.warning("Couldn't open first post under hashtag.")
            continue

        logger.info("Collecting likers from the post...")
        likers = scroll_and_collect_likers(device, plugin_state)

        if not likers:
            logger.info("No likers found.")
            continue

        logger.info(f"Collected {len(likers)} likers, starting interaction...")

        for liker in likers:
            if not quota_supervisor.check_and_log("interactions"):
                logger.info("Reached interaction quota.")
                break

            if state.already_interacted_with(liker):
                logger.debug(f"Already interacted with {liker}, skipping.")
                continue

            success = interact_with_user(session_state, liker)
            if success:
                logger.info(f"Interacted with {liker}.")
                state.mark_interacted(liker)
            else:
                logger.info(f"Failed to interact with {liker}, skipping.")

        # Optional: return or break after one post if desired
        if args.single_post:
            break
def handle_posts(device, username, sessions, likes_limit, on_interaction, my_username, is_likers=False):
    interacted = 0

    # Open the first post
    if not open_first_post(device):
        print("Failed to open the first post.")
        return interacted

    post_counter = 0
    while interacted < likes_limit:
        if post_counter > 0:
            if not swipe_to_next_post(device):
                print("Couldn't swipe to next post. Possibly reached the end or hit a problem.")
                break

        post_counter += 1
        print(f"Opening post #{post_counter}...")

        # Wait for post content to load
        if not wait_for_post_to_load(device):
            print("Post did not load correctly.")
            continue

        # Get username of post owner
        post_owner = get_post_owner_username(device)
        if not post_owner:
            print("Couldn't fetch post owner username.")
            continue

        # Skip interacting with our own posts
        if post_owner.lower() == my_username.lower():
            print("Skipping own post.")
            continue

        # Interact with the user
        interacted_successfully = interact_with_user(
            device=device,
            username=post_owner,
            sessions=sessions,
            my_username=my_username,
            interaction_type="post",
            is_likers=is_likers,
            on_interaction=on_interaction
        )

        if interacted_successfully:
            interacted += 1
            print(f"Interacted with @{post_owner} ({interacted}/{likes_limit})")

    print(f"Done handling posts. Total interactions: {interacted}")
    return interacted
def handle_followers(
    self,
    device,
    session_state,
    username,
    current_job,
    storage,
    on_interaction,
    interaction,
    is_follow_limit_reached,
    scroll_end_detector,
):
    is_myself = username == session_state.my_username
    if not nav_to_blogger(device, username, current_job):
        return

    iterate_over_followers(
        self,
        device,
        session_state,
        username,
        current_job,
        storage,
        on_interaction,
        interaction,
        is_follow_limit_reached,
        scroll_end_detector,
        is_myself,
    )


def iterate_over_followers(
    self,
    device,
    session_state,
    username,
    current_job,
    storage,
    on_interaction,
    interaction,
    is_follow_limit_reached,
    scroll_end_detector,
    is_myself,
):
    container = device.find(
        resourceId=self.ResourceID.FOLLOW_LIST_CONTAINER,
        className=ClassName.LINEAR_LAYOUT,
    )
    container.wait(Timeout.LONG)

    def scrolled_to_top():
        return device.find(
            resourceId=self.ResourceID.ROW_SEARCH_EDIT_TEXT,
            className=ClassName.EDIT_TEXT,
        ).exists()

    while True:
        logger.info("Iterate over visible followers.")
        screen_usernames = []
        skipped_count = 0
        scroll_end_detector.notify_new_page()

        user_list = device.find(resourceIdMatches=self.ResourceID.USER_LIST_CONTAINER)
        row_height, n_users = inspect_current_view(user_list)

        try:
            for item in user_list:
                if item.get_height() < row_height:
                    continue

                username_view = item.child(index=1).child(index=0).child()
                if not username_view.exists():
                    logger.info("End of visible list reached.")
                    break

                follower = username_view.get_text()
                screen_usernames.append(follower)
                scroll_end_detector.notify_username_iterated(follower)

                # Blacklist or already interacted
                if storage.is_user_in_blacklist(follower):
                    logger.info(f"@{follower} is in blacklist. Skip.")
                    continue

                interacted, interacted_when = storage.check_user_was_interacted(follower)
                if interacted and not storage.can_be_reinteract(
                    interacted_when, get_value(self.args.can_reinteract_after, None, 0)
                ):
                    logger.info(
                        f"@{follower} already interacted on {interacted_when:%Y/%m/%d %H:%M:%S}. Skipping."
                    )
                    skipped_count += 1
                    continue

                logger.info(f"@{follower}: interacting...", extra={"color": Fore.YELLOW})
                if username_view.click_retry():
                    if not interact(
                        storage=storage,
                        is_follow_limit_reached=is_follow_limit_reached,
                        username=follower,
                        interaction=interaction,
                        device=device,
                        session_state=session_state,
                        current_job=current_job,
                        target=username,
                        on_interaction=on_interaction,
                    ):
                        return
                    device.back()
        except IndexError:
            logger.warning("Possibly reached end of screen unexpectedly.")

        # Scroll logic
        if is_myself and scrolled_to_top():
            logger.info("Scrolled to top — finished.", extra={"color": Fore.GREEN})
            return

        if not screen_usernames:
            logger.info("No users to iterate — ending.")
            return

        load_more_btn = device.find(resourceId=self.ResourceID.ROW_LOAD_MORE_BUTTON)
        retry_btn = load_more_btn.child(
            className=ClassName.IMAGE_VIEW,
            descriptionMatches=case_insensitive_re("Retry"),
        ) if load_more_btn.exists() else None

        list_view = device.find(resourceId=self.ResourceID.LIST, className=ClassName.LIST_VIEW)
        if not list_view.exists():
            logger.error("Follower list view not found, pressing back.")
            device.back()
            continue

        if scroll_end_detector.is_the_end():
            logger.info("Scroll end detected — finishing.")
            return

        all_skipped = skipped_count == len(screen_usernames)
        if retry_btn and retry_btn.exists():
            logger.info("Clicking retry on Load More.")
            retry_btn.click_retry()
            random_sleep(5, 10, modulable=False)
        elif all_skipped:
            scroll_end_detector.notify_skipped_all()
            if scroll_end_detector.is_skipped_limit_reached():
                return
            if scroll_end_detector.is_fling_limit_reached():
                logger.info("Flinging down — skip limit hit.")
                list_view.fling(Direction.DOWN)
            else:
                logger.info("Scrolling down — all users skipped.")
                list_view.scroll(Direction.DOWN)
        else:
            logger.info("Scrolling to load next set of users.")
            list_view.scroll(Direction.DOWN)
