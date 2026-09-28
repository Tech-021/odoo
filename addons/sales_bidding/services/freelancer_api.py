import logging

import requests


_logger = logging.getLogger(__name__)


class FreelancerAPIError(Exception):
    pass


class FreelancerAPI:
    BASE_URL = "https://www.freelancer.com/api/projects/0.1"

    def __init__(self, access_token, client_id=None, client_secret=None):
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self.session.headers.update({"Authorization": "Bearer %s" % access_token})
        if client_id:
            self.session.headers["freelancer-oauth-v1"] = client_id

    def _get(self, path, params=None):
        try:
            # Keep a bad/unreachable Freelancer endpoint from blocking an
            # Odoo worker or a manual settings request for several minutes.
            response = self.session.get(
                self.BASE_URL + path,
                params=params,
                timeout=(10, 20),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise FreelancerAPIError("Freelancer API request failed: %s" % error) from error
        if payload.get("status") == "error":
            message = payload.get("message") or "Freelancer API returned an error"
            raise FreelancerAPIError(message)
        return payload

    @staticmethod
    def _items(payload, key):
        result = payload.get("result") or payload
        if isinstance(result, dict):
            return result.get(key) or []
        return result if isinstance(result, list) else []

    def _paged(self, path, params, key):
        items = []
        offset = 0
        page = 0
        while True:
            page_params = dict(params or {})
            page_params.update({"offset": offset, "limit": 100})
            payload = self._get(path, page_params)
            batch = self._items(payload, key)
            items.extend(batch)
            _logger.info(
                "Freelancer API: %s page %s returned %s %s",
                path,
                page + 1,
                len(batch),
                key,
            )
            result = payload.get("result") or payload
            total = result.get("total_count") if isinstance(result, dict) else None
            if not batch or len(batch) < 100 or (total is not None and len(items) >= total):
                _logger.info(
                    "Freelancer API: %s pagination complete; total received: %s",
                    path,
                    len(items),
                )
                return items
            page += 1
            offset += len(batch)

    def get_projects(self, freelancer_user_id, from_time=None):
        params = {"bidders[]": freelancer_user_id}
        if from_time:
            params["from_time"] = int(from_time)
        return self._paged("/projects", params, "projects")

    def get_project_bids(self, project_id):
        return self._paged("/projects/%s/bids" % project_id, {}, "bids")

    @staticmethod
    def find_our_bid(bids, freelancer_user_id):
        return next(
            (bid for bid in bids if str(bid.get("bidder_id")) == str(freelancer_user_id)),
            None,
        )
