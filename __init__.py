from re import L
from flask import render_template, Blueprint, request
import os, datetime

from CTFd.models import Users, Challenges, Awards, Solves, Teams
from sqlalchemy.sql import and_
from sqlalchemy.orm import joinedload
from CTFd.utils.scores import get_standings, get_user_standings
from CTFd.utils.plugins import override_template
from CTFd.utils import get_config
from CTFd.utils.modes import TEAMS_MODE, generate_account_url, get_mode_as_word
from CTFd.utils import config
from CTFd.utils.decorators.visibility import check_score_visibility, check_account_visibility
from CTFd.utils.helpers import get_infos
from CTFd.utils.config.visibility import scores_visible
from CTFd.utils.user import is_admin
from collections import defaultdict
from CTFd.cache import cache, make_cache_key
from CTFd.utils.dates import isoformat, unix_time_to_utc
from CTFd.plugins import register_plugin_assets_directory
from CTFd.utils.logging import log


def get_all_categories():
    challenges = (
        Challenges.query.filter(
            and_(Challenges.state != "hidden", Challenges.state != "locked")
        )
            .order_by(Challenges.value)
            .all()
    )
    categories_list = set()
    for challenge in challenges:
        categories_list.add(challenge.category)
    return list(categories_list)

def get_single_rank_predata(standings):
    team_ids = [team.account_id for team in standings]

    solves = Solves.query.filter(Solves.account_id.in_(team_ids))
    awards = Awards.query.filter(Awards.account_id.in_(team_ids))

    freeze = get_config("freeze")

    if freeze:
        solves = solves.filter(Solves.date < unix_time_to_utc(freeze))
        awards = awards.filter(Awards.date < unix_time_to_utc(freeze))

    if 'category' in request.args and request.args['category'] and request.args['category'] != 'All':
        category_challenges = Challenges.query.filter(Challenges.category == request.args['category']).all()
        category_challenges_id = [category_challenge.id for category_challenge in category_challenges]
        solves = solves.filter(Solves.challenge_id.in_(category_challenges_id))
        awards = awards.filter(Awards.category == request.args['category'])

    solves = solves.all()
    awards = awards.all()
    # Build a mapping of accounts to their solves and awards
    solves_mapper = defaultdict(list)
    for solve in solves:
        solves_mapper[solve.account_id].append(
            {
                "challenge_id": solve.challenge_id,
                "account_id": solve.account_id,
                "team_id": solve.team_id,
                "user_id": solve.user_id,
                "value": solve.challenge.value,
                "date": isoformat(solve.date),
            }
        )
    
    # Sort all solves & awards by date
    for team_id in solves_mapper:
        solves_mapper[team_id] = sorted(
            solves_mapper[team_id], key=lambda k: k["date"]
        )

    pre_data = []
    if request.args['category'] == 'All':
        awards_mapper = defaultdict(list)
        for award in awards:
            awards_mapper[award.account_id].append(
                {
                    "challenge_id": None,
                    "account_id": award.account_id,
                    "team_id": award.team_id,
                    "user_id": award.user_id,
                    "value": award.value,
                    "date": isoformat(award.date),
                }
            )
        for team_id in awards_mapper:
            awards_mapper[team_id] = sorted(
                awards_mapper[team_id], key=lambda k: k["date"]
            )
        for i, standing in enumerate(standings):
            solves = solves_mapper.get(standing.account_id, [])
            awards = awards_mapper.get(standing.account_id, [])
            solves_len, awards_len = len(solves), len(awards)
            if solves_len == 0 and awards_len == 0: continue
            last_point_time = max([_["date"] for _ in solves] + [_["date"] for _ in awards])
            scores = sum([_["value"] for _ in solves] + [_["value"] for _ in awards])
            pre_data.append({
                "id": standing.account_id,
                "name": standing.name,
                "solves_len": solves_len,
                "awards_len": awards_len,
                "solves_awards": sorted(solves + awards, key=lambda k: k['date']),
                "last_point_time": last_point_time,
                "scores": scores
            })
    else:
        for i, standing in enumerate(standings):
            solves = solves_mapper.get(standing.account_id, [])
            solves_len = len(solves)
            if len(solves) == 0: continue
            last_point_time = max([_["date"] for _ in solves])
            scores = sum([_["value"] for _ in solves])
            pre_data.append({
                "id": standing.account_id,
                "name": standing.name,
                "solves_len": solves_len,
                "awards_len": 0,
                "solves_awards": solves,
                "last_point_time": last_point_time,
                "scores": scores
            })

    pre_data = sorted(pre_data, key=lambda x:(-x["scores"], x["last_point_time"]))
    return pre_data

def load(app):
    single_rank = Blueprint(
        'single_rank',
         __name__, 
         template_folder='templates',
         static_folder='assets',
    )
    register_plugin_assets_directory(app, base_path="/plugins/ctfd-single_rank/assets")

    # @cache.memoize(timeout=60)
    def query_single_rank_list():
        standings = get_standings()
        pre_data = get_single_rank_predata(standings)
        return pre_data
        
    @single_rank.route('/scoreboard/top', methods=["GET"])
    @check_score_visibility
    @check_account_visibility
    def get_single_rank_list():
        response = []
        pre_data = query_single_rank_list()
        for i, data in enumerate(pre_data):
            response.append({
                "pos": i + 1,
                "account_id": data["id"],
                "account_url": generate_account_url(account_id = data["id"]),
                "oauth_id": None,
                "name": data["name"],
                "scores": data["scores"],
                "solves_len": data["solves_len"],
                "awards_len": data["awards_len"],               
                "last_point_time": data["last_point_time"]
            })
        return {"success": True, "data": response}

    @single_rank.route('/scoreboard/top/<int:count>', methods=["GET"])
    @check_score_visibility
    @check_account_visibility
    def get_single_rank_detail(count):
        response = {}
        pre_data = query_single_rank_list()
        if len(pre_data) >= int(count): pre_data = pre_data[:count]
        for i, data in enumerate(pre_data):
            response[i + 1] = pre_data[i]
        return {"success": True, "data": response}

    @single_rank.route('/scoreboard', methods=['GET'])
    @check_score_visibility
    @check_account_visibility
    def view_single_rank():
        # override templates
        dir_path = os.path.dirname(os.path.realpath(__file__))
        template_path = os.path.join(dir_path, 'templates')
        template_path = os.path.join(template_path, 'scoreboard.html')
        override_template("scoreboard.html", open(template_path).read())
        
        infos = get_infos()
    
        if config.is_scoreboard_frozen():
            infos.append("Scoreboard has been frozen")
    
        if is_admin() is True and scores_visible() is False:
            infos.append("Scores are not currently visible to users")
        
        # get categories
        categories = get_all_categories()

        return render_template("scoreboard.html", categories=categories, infos=infos)
    
    app.register_blueprint(single_rank)
    app.view_functions['scoreboard.listing'] = view_single_rank