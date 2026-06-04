#!/usr/bin/env bash
# Single source of truth for the dub-cli version. Sourced by bin/dub
# (for --version) and by lib/env.sh (for the User-Agent header sent on
# Kyma calls so Kyma can attribute usage and detect stale installs).
#
# To cut a release: bump DUB_CLI_VERSION below, open a release PR titled
# `release: vX.Y.Z`, merge, then tag the merge commit `vX.Y.Z` and push.

export DUB_CLI_VERSION="0.1.0"
export DUB_CLI_VERSION_STRING="dub-cli v${DUB_CLI_VERSION}"
