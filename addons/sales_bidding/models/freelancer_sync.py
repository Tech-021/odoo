import logging
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo import SUPERUSER_ID

from ..services.freelancer_api import FreelancerAPI, FreelancerAPIError


_logger = logging.getLogger(__name__)


class SalesBidFreelancerSync(models.AbstractModel):
    _name = "sales.bid.freelancer.sync"
    _description = "Freelancer Sales Bid Synchronization"

    @api.model
    def sync_freelancer_bids(self):
        # Scheduled actions normally execute as Odoo's superuser.  Manual
        # calls still require the Sales Bidding Manager group.
        if self.env.uid != SUPERUSER_ID and not self.env.user.has_group(
            "sales_bidding.group_sales_bidding_manager"
        ):
            raise UserError(_("Only Sales Bidding Managers can synchronize Freelancer bids."))
        params = self.env["ir.config_parameter"].sudo()
        if params.get_param("sales_bidding.freelancer_enabled") != "True":
            raise UserError(_("Freelancer integration is not enabled."))
        token = params.get_param("sales_bidding.freelancer_access_token")
        user_id = params.get_param("sales_bidding.freelancer_user_id")
        if not token or not user_id:
            raise UserError(_("Configure the Freelancer access token and user ID first."))

        api = FreelancerAPI(
            token,
            params.get_param("sales_bidding.freelancer_client_id"),
            params.get_param("sales_bidding.freelancer_client_secret"),
        )
        stats = {"projects": 0, "created": 0, "existing": 0, "skipped": 0, "errors": 0}
        last_sync = params.get_param("sales_bidding.freelancer_last_sync")
        try:
            last_timestamp = int(last_sync) if last_sync else 0
        except ValueError:
            last_timestamp = 0

        initial_days = int(params.get_param("sales_bidding.freelancer_initial_sync_days", 30))
        if not last_timestamp:
            last_timestamp = int(datetime.now(timezone.utc).timestamp()) - initial_days * 86400
            _logger.info(
                "Freelancer sync: first sync; importing bids from the last %s days",
                initial_days,
            )
        else:
            _logger.info(
                "Freelancer sync: importing bids newer than timestamp %s",
                last_timestamp,
            )

        _logger.info(
            "Freelancer sync configuration: account user ID %s, from_time %s",
            user_id,
            last_timestamp,
        )
        try:
            projects = api.get_projects(user_id, from_time=last_timestamp)
        except FreelancerAPIError as error:
            _logger.warning("Freelancer sync failed while loading projects: %s", error)
            raise UserError(_("Freelancer sync failed: %s") % error) from error
        _logger.info("Freelancer sync: %s projects received", len(projects))

        for project in projects:
            project_id = project.get("id")
            if not project_id:
                stats["skipped"] += 1
                _logger.warning("Freelancer sync: skipped project without an ID")
                continue
            stats["projects"] += 1
            _logger.info(
                "Freelancer sync: checking project %s (%s/%s)",
                project_id,
                stats["projects"],
                len(projects),
            )
            try:
                project_bids = api.get_project_bids(project_id)
                _logger.info(
                    "Freelancer sync: project %s returned %s bids",
                    project_id,
                    len(project_bids),
                )
                bid = api.find_our_bid(project_bids, user_id)
                if not bid:
                    stats["skipped"] += 1
                    _logger.info(
                        "Freelancer sync: project %s skipped; no bid found for configured account",
                        project_id,
                    )
                    continue
                bid_id = str(bid.get("id"))
                if not bid_id or bid_id == "None":
                    stats["skipped"] += 1
                    _logger.warning(
                        "Freelancer sync: project %s skipped; matching bid has no ID",
                        project_id,
                    )
                    continue
                _logger.info(
                    "Freelancer sync: matching bid %s found for project %s",
                    bid_id,
                    project_id,
                )
                existing = self.env["sales.bid"].sudo().search([
                    ("platform", "=", "freelancer"),
                    ("freelancer_bid_id", "=", bid_id),
                ], limit=1)
                if existing:
                    stats["existing"] += 1
                    _logger.info(
                        "Freelancer sync: bid %s already exists as sales.bid %s",
                        bid_id,
                        existing.id,
                    )
                    continue
                timestamp = int(bid.get("time_submitted") or 0)
                if not timestamp or timestamp <= last_timestamp:
                    stats["skipped"] += 1
                    _logger.info(
                        "Freelancer sync: bid %s skipped; timestamp %s is outside sync window",
                        bid_id,
                        timestamp or "missing",
                    )
                    continue
                bid_date = datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
                now = fields.Datetime.to_datetime(fields.Datetime.now())
                if bid_date > now:
                    bid_date = now
                project_url = project.get("url") or project.get("project_url")
                if not project_url:
                    project_url = "https://www.freelancer.com/projects/%s" % project_id
                project_title = project.get("title") or bid.get("project_title") or str(project_id)
                job_type = bid.get("type") or project.get("type") or project.get("project_type")
                bid_type = "hourly" if str(job_type).lower() in ("hourly", "hourly_project") else "fixed"
                self.env["sales.bid"].sudo().create({
                    "name": project_title,
                    "salesperson_id": False,
                    "platform": "freelancer",
                    "job_url": project_url,
                    "bid_amount": float(bid.get("amount") or 0.0),
                    "bid_type": bid_type,
                    "status": "submitted",
                    "bid_date": bid_date,
                    "notes": bid.get("description") or False,
                    "freelancer_bid_id": bid_id,
                    "freelancer_project_id": str(project_id),
                })
                stats["created"] += 1
                _logger.info(
                    "Freelancer sync: bid %s imported successfully for project %s",
                    bid_id,
                    project_id,
                )
            except (FreelancerAPIError, ValueError, TypeError) as error:
                stats["errors"] += 1
                _logger.exception(
                    "Freelancer sync: project %s failed: %s",
                    project_id,
                    error,
                )

        params.set_param("sales_bidding.freelancer_last_sync", str(int(datetime.now(timezone.utc).timestamp())))
        _logger.info(
            "Freelancer sync completed: projects=%s, imported=%s, already imported=%s, skipped=%s, errors=%s",
            stats["projects"],
            stats["created"],
            stats["existing"],
            stats["skipped"],
            stats["errors"],
        )
        return stats
