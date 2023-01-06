import requests
from typing import List
from utils.base_logger import logger
from data.replay_info import ReplayInfo
from data.ladder_user_info import LadderUserInfo
from modules.ladder_retriever import LadderRetriever
from utils.request_utils import get_soup_from_url, get_response_from_url
from utils.constants import MAX_USERS, REPLAY_BASE_URL
from utils.errors import LadderNotFoundException

REPLAY_SEARCH_BASE_URL = (
    "https://replay.pokemonshowdown.com/search/?output=html&page=1&user="
)


class ReplayHandler:
    def __init__(
        self,
        format_id: str,
        ladder_retriever: LadderRetriever,
    ):
        self.format_id = format_id
        self.ladder_retriever = ladder_retriever

    def extract_replays(self, num_users_to_pull: int = MAX_USERS) -> List[ReplayInfo]:
        """
        Retrieve replays from top-rated ladder users

        :param: num_users_to_pull number of users (ie. teams) to retrieve
        :returns: list of most recent replay from each user
        """
        # Limit if greater than MAX_USERS
        num_users_to_pull = min(num_users_to_pull, MAX_USERS)

        top_ladder_users = self.ladder_retriever.get_users(self.format_id)
        if not top_ladder_users:
            logger.warning("Could not retrieve ladder rankings, aborting...")
            raise LadderNotFoundException(
                "Could not retrieve ladder rankings for {format}".format(
                    format=self.format_id
                )
            )

        replay_info_list = []
        teams_found = 0
        for user_info in top_ladder_users:
            most_recent_replay_id = self._get_most_recent_replay_id(user_info.username)
            if not most_recent_replay_id:
                logger.info(
                    "No '{format}' replays found for {username}, continuing to next".format(
                        format=self.format_id, username=user_info.username
                    )
                )
            else:
                logger.info(
                    "Found '{format}' replay for {username}".format(
                        format=self.format_id, username=user_info.username
                    )
                )
                replay_info = self._get_replay_info(user_info, most_recent_replay_id)
                replay_info_list.append(replay_info)
                teams_found += 1
                if teams_found == num_users_to_pull:
                    break

        return replay_info_list

    """
    Retrieve most recent format replay ID given a user

    :param: username Username to search replays for
    :returns: ID of most recent format replay, empty string if not found or time out
    """

    def _get_most_recent_replay_id(self, username: str) -> str:
        replay_search_url = REPLAY_SEARCH_BASE_URL + username
        try:
            replay_search_soup = get_soup_from_url(replay_search_url)
            # Assume replays are sorted reverse-chronologically
            replay_id = [
                # Remove `/` character for replay ID
                # eg. <a href="/gen8vgc2020-1197324298" data-target="push"><small>...
                replay.get("href")[1:]
                for replay in replay_search_soup.find_all(
                    lambda predicate: predicate.name == "a"
                    and self.format_id in predicate.get("href")
                )
            ]
            return replay_id[0] if replay_id else ""
        except Exception as e:
            logger.warning(
                "Unable to reach server for replays: {err}".format(err=str(e))
            )
            return ""

    def _get_replay_info(self, user_info: LadderUserInfo, replay_id: str) -> ReplayInfo:
        """
        Retrieve replay metadata info by transforming user info and replay ID

        :param: user_info Associated user metadata
        :param: replay_id Replay ID to retrieve
        :returns: ReplayInfo
        """
        try:
            replay_json = self._get_replay_json_from_id(replay_id)
            replay_info = ReplayInfo(
                replay_json["id"],
                user_info.username,
                user_info.rating,
                replay_json["format"],
                replay_json["log"],
                replay_json["uploadtime"],
            )
            return replay_info
        except KeyError as key_e:
            logger.error("Replay key not found")
            raise key_e
        except Exception as e:
            logger.error("Unable to retrieve replay: {err}".format(err=str(e)))

    """
    Retrieve replay JSON from PS servers given an ID

    :param: replay_id 
    :returns: replay metadata JSON
    """

    def _get_replay_json_from_id(self, replay_id: str) -> dict:
        try:
            replay_data_get_url = REPLAY_BASE_URL + replay_id + ".json"
            replay_data_res = get_response_from_url(replay_data_get_url)
            return {} if not replay_data_res else replay_data_res.json()
        except requests.exceptions.RequestException as e:
            raise e
