# Copyright 2021 Canonical Limited.
#
# This file is part of juju-verify.
#
# juju-verify is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# juju-verify is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see https://www.gnu.org/licenses/.
"""ceph-osd verification."""
import logging
from typing import Set

from juju.unit import Unit

from juju_verify.utils.action import data_from_action
from juju_verify.utils.unit import verify_charm_unit, run_action_on_units
from juju_verify.verifiers.base import BaseVerifier
from juju_verify.verifiers.result import aggregate_results, Result

logger = logging.getLogger()


class CephCommon(BaseVerifier):  # pylint: disable=W0223
    """Parent class for CephMon and CephOsd verifier."""

    @classmethod
    def check_cluster_health(cls, *units: Unit) -> Result:
        """Check Ceph cluster health for specific units.

        This will execute `get-health` against each unit provided.
        """
        verify_charm_unit("ceph-mon", *units)
        result = Result(success=True)
        action_map = run_action_on_units(list(units), "get-health")
        for unit, action in action_map.items():
            cluster_health = data_from_action(action, "message")
            logger.debug("Unit (%s): Ceph cluster health '%s'", unit, cluster_health)

            if "HEALTH_OK" in cluster_health and result.success:
                result += Result(True, f"{unit}: Ceph cluster is healthy")
            elif "HEALTH_WARN" in cluster_health or "HEALTH_ERR" in cluster_health:
                result += Result(False, f"{unit}: Ceph cluster is unhealthy")
            else:
                result += Result(False, f"{unit}: Ceph cluster is in an unknown state")

        if not action_map:
            result = Result(success=False, reason="Ceph cluster is in an unknown state")

        return result


class CephOsd(CephCommon):
    """Implementation of verification checks for the ceph-osd charm."""

    NAME = 'ceph-osd'

    def get_ceph_mon_units(self) -> Set[Unit]:
        """Get Ceph-mon units related to verified units.

        1. get all distinct ceph-osd applications from provides units
        2. get all relationships based on found apps or ceph-mon
        3. get the first unit from the application providing the relation
        """
        # get all affected ceph-osd applications
        applications = {unit.application for unit in self.units}
        logger.debug("affected applications %s", map(str, applications))
        applications.add("ceph-osd")

        # get all relation between ceph-osd and ceph-mon
        relations = {relation for relation in self.model.relations
                     if any(relation.matches(f"{application}:mon")
                            for application in applications)}
        logger.debug("found relations %s", map(str, relations))

        # get first ceph-mon unit from relation
        ceph_mon_units = {relation.provides.application.units[0]
                          for relation in relations}
        logger.debug("found units %s", map(str, ceph_mon_units))

        return ceph_mon_units

    def verify_reboot(self) -> Result:
        """Verify that it's safe to reboot selected ceph-osd units."""
        return aggregate_results(self.check_cluster_health(*self.get_ceph_mon_units()))

    def verify_shutdown(self) -> Result:
        """Verify that it's safe to shutdown selected ceph-osd units."""
        return self.verify_reboot()