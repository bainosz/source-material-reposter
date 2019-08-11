import praw
import configparser
import time


config = configparser.ConfigParser()
config.read('config.ini')

reddit = praw.Reddit(**config['Auth'])


def repost(comment):
    # Build comment
    user = f'/u/{comment.author.name}'
    parent = comment.parent()
    if isinstance(parent, praw.models.Comment):
        parent_link_template = config['Options']['parent_link_template']
        parent = parent_link_template.format(link=parent.permalink)
    else:
        parent = config['Options']['parent_none_template']
    body = comment.body

    repost_template = config['Options']['repost_template']
    message = repost_template.format(user=user, parent=parent, body=body)

    # Submit
    source_corner = select_source_corner(comment)
    if source_corner is None:
        print('ERROR: Could not find Source Corner for comment')
        return None

    print(f'Reposting comment {comment.id}:')
    print(f'  as a reply to Source Corner ({source_corner.id})')
    print('### Message Start ###')
    print(message)
    print('### Message end ###')

    return source_corner.reply(message)


def select_source_corner(comment):
    # Get the discussion post and check is episode discussion
    submission = comment.submission
    print(f'Selecting the Source Corner for submission {submission.id}')

    if submission.author.name != config['Options']['episode_bot_account']:
        print('  ! Unexpected submission author')
        return None

    # Get the top comment and check it is the Source Corner
    top_comment = submission.comments[0]
    if not top_comment.stickied:
        print('  ! Top comment is not stickied')
        return None
    if top_comment.author.name != config['Options']['sc_bot_account']:
        print('  ! Unexpected top comment author')
        return None

    return top_comment


def get_all_sc_removals(modlog, last_timestamp):
    sc_removals = list()
    for action in modlog:
        if action.created_utc < last_timestamp:
            break
        if action.action != 'distinguish':
            continue

        if is_sc_removal(action):
            url = 'https://www.reddit.com' + action.target_permalink
            action_comment = reddit.comment(url=url)
            sc_removals.append(action_comment.parent())

    print(f'Collected {len(sc_removals)} source corner removals')
    return sc_removals


def is_sc_removal(action):
    # SC removals are detected via the removal reason
    if action.action != 'distinguish':
        return False

    # Do not pick the source corner itself
    if action.mod.name == config['Options']['sc_bot_account']:
        return False

    body = action.target_body.lower()
    # Removal message must mention the source corner
    if not ('source corner' in body or 'source material' in body):
        return False

    # If the comment was removed for spoilers, don't repost it
    if 'spoiler' in body:
        return False

    # Make sure the post is an episode discussion post
    url = 'https://www.reddit.com' + action.target_permalink
    action_comment = reddit.comment(url=url)
    submission = action_comment.submission
    if submission.author.name != config['Options']['episode_bot_account']:
        return False

    return True


def scan_modlog_once(subreddit, last_timestamp):
    sc_removals = get_all_sc_removals(subreddit.mod.log(), last_timestamp)

    for removal in sc_removals:
        try:
            repost(removal)
        except Exception as e:
            print(f'ERROR: Could not repost {removal.id}')
            print(f'  {type(e).__name__}: {str(e)}')
            print(f'  Link: {removal.permalink}')

    return len(sc_removals) > 0


def scan_modlog_loop(subreddit):
    last_timestamp = time.time()
    sleep_time = int(config['Options']['sleep_time'])
    active = True

    while True:
        #print(f'Sleeping for {sleep_time} seconds')
        time.sleep(sleep_time)

        print('Scanning modlog...')
        active = scan_modlog_once(subreddit, last_timestamp)
        last_timestamp = time.time()

        #print('Done')


if __name__ == '__main__':
    subreddit = reddit.subreddit(config['Options']['subreddit'])
    scan_modlog_loop(subreddit)
