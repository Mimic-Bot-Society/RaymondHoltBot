import os
import random
import threading
import time
import re
from random import randrange

import praw
import psycopg2
from colorama import init, Fore, Style
from praw.exceptions import RedditAPIException

reply_rate_limit_sleep = 10

general_rate_limit_sleep = 2


def read_file_contents(_file_name):
    with open(_file_name, "r") as file:
        file_contents = file.read()
    return file_contents


def get_quotes():
    return get_all_from_table("quote")


def get_triggers():
    return get_all_from_table("trigger")


def get_quote_triggers():
    return get_all_from_table("quote_trigger")


def get_all_from_table(_table):
    connection = psycopg2.connect(get_database_url(), sslmode='require')
    cursor = connection.cursor()
    cursor.execute(f"select * from {_table}")
    fields = [field_md[0] for field_md in cursor.description]
    result = [dict(zip(fields, row)) for row in cursor.fetchall()]
    return result


def get_random_quote():
    return quotes[randrange(0, len(quotes))]['text']


def get_matched_quote(_comment_body):
    trigger = next((tag for tag in (map(lambda item: item['trigger'], triggers)) if tag in _comment_body), None)
    if trigger is None:
        return get_random_quote()
    trigger_id = next((item for item in triggers if item['trigger'] == trigger), None)['id']
    quote_id = next((item for item in quote_triggers if item['trigger_id'] == trigger_id), None)['quote_id']
    return next((item for item in quotes if item['id'] == quote_id), None)['text']


def handle_comment(_comment):
    _comment.replies.replace_more(limit=None)
    replies = _comment.replies.list()
    handle_single_comment(_comment, 0)
    if len(replies) > 0:
        for comment_replay in replies:
            time.sleep(random.randint(1, general_rate_limit_sleep))
            handle_comment(comment_replay)


def is_replying():
    return os.getenv("is_replying", False) == "True"


def get_allowed_subs():
    return os.getenv("allowed_subs", "test")


def get_trigger_word():
    return os.getenv("trigger_word", "protagonist")


def get_bot_username():
    return os.getenv("username", "TheProtagonistBot")


def get_database_url():
    return os.getenv("DATABASE_URL", "")


def handle_rate_limit_exception(_message, _comment):
    seconds = calculate_break_time(_message)
    print(f"Rate limit exception, sleeping for {seconds} seconds then retrying!")
    thread = threading.Thread(target=handle_single_comment, args=(_comment, seconds,))
    thread.start()


def calculate_break_time(_message):
    p_seconds = re.compile(r"\d+ seconds", re.IGNORECASE)
    p_minutes = re.compile(r"\d+ minutes", re.IGNORECASE)
    seconds_match = p_seconds.findall(_message)
    minutes_match = p_minutes.findall(_message)
    if len(seconds_match) > 0:
        seconds = int(seconds_match[0].replace("seconds", "").strip())
    elif len(minutes_match) > 0:
        seconds = int(minutes_match[0].replace("minutes", "").strip()) * 60
    else:
        seconds = 600
    seconds += random.randint(10, 30)
    return seconds


def is_replied_to_it(_replies):
    if len(_replies) > 0:
        return any(reply for reply in _replies if reply.author.name == get_bot_username())
    else:
        return False


def handle_single_comment(_single_comment, _sleep):
    if _sleep != 0:
        time.sleep(_sleep)

    comment_body = _single_comment.body.lower()
    if get_trigger_word() in comment_body and _single_comment.author.name != get_bot_username():
        try:
            reply_body = get_reply_body(comment_body)
            sub_name = _single_comment.subreddit.display_name
            print(f"{Fore.GREEN}Comment:")
            print(f"{Fore.YELLOW}###")
            print(f"{Fore.BLUE}{comment_body}")
            print(f"{Fore.YELLOW}###")
            already_replied = is_replied_to_it(_single_comment.replies.list())
            author = "u/deleted" if _single_comment.author is None else f"u/{_single_comment.author}"
            reply_body = f"Dear {author},  \n{reply_body}  \nSincerely,  \nRaymond Holt"
            print(f"{Fore.GREEN}Reply:")
            print(f"{Fore.BLUE}{reply_body}")
            if is_replying() and sub_name in get_allowed_subs().split("+") and not already_replied:
                print(f"Replying to comment: {_single_comment.id}, Wait...{Style.RESET_ALL}")
                time.sleep(random.randint(1, reply_rate_limit_sleep))
                _single_comment.reply(reply_body)
                print(f"{Fore.GREEN}Replied to comment.")
            else:
                print(f"{Fore.RED}Reply is forbidden in this subreddit: {Fore.CYAN}{sub_name}{Style.RESET_ALL}")
                print(f"{Fore.RED}Because:")
                print(f"{Fore.RED}generally replying allowance is:{Style.RESET_ALL}", end='')
                print(f"{Fore.CYAN} {is_replying()}{Style.RESET_ALL}")
                print(f"{Fore.RED}, Or bot already replied to this comment:{Style.RESET_ALL}", end='')
                print(f"{Fore.CYAN} {already_replied}{Style.RESET_ALL}")
        except RedditAPIException as reddit_api_exception:
            message = reddit_api_exception.args[0].message
            print(f"{Fore.RED}Reddit API Exception: {Fore.CYAN}{message}{Style.RESET_ALL}")
            handle_rate_limit_exception(message, _single_comment)
        except Exception as e:
            print(f"{Fore.RED}Failed to reply to comment by {_single_comment.author}{Style.RESET_ALL}")
            print(f"{Fore.RED}Exception: {Fore.CYAN}{str(e)}")
    else:
        print(f"{Fore.RED}Invalid comment: {Fore.CYAN}{_single_comment.id}{Style.RESET_ALL}")


def get_reply_body(comment_body):
    match = get_matched_quote(comment_body)
    return match if match is not None else get_random_quote()


init()

print(f"{Fore.YELLOW}Starting bot...")
print(f"Trigger word: {Fore.GREEN}{get_trigger_word()}")

print(f"{Fore.YELLOW}Getting quotes...")
quotes = get_quotes()
print(f"{Fore.YELLOW}Getting triggers...")
triggers = get_triggers()
print(f"{Fore.YELLOW}Getting quote triggers...")
quote_triggers = get_quote_triggers()

print(f"{Fore.YELLOW}Getting reddit instance... for user: {Fore.GREEN}{get_bot_username()}")
reddit = praw.Reddit(
    client_id=os.getenv("client_id"),
    client_secret=os.getenv("client_secret"),
    user_agent=os.getenv("user_agent"),
    username=os.getenv("username"),
    password=os.getenv("password")
)

print(f"{Fore.YELLOW}Getting subreddits...")
subs = reddit.subreddit(get_allowed_subs())

print(f"{Fore.YELLOW}Getting comments...{Style.RESET_ALL}")
for comment in subs.stream.comments():
    time.sleep(random.randint(1, general_rate_limit_sleep))
    comment.refresh()
    handle_comment(comment)
