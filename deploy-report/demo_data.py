"""Fake data for --demo mode. Shaped identically to what discovery/ecs.py
and discovery/eks.py return for real, so report_renderer.py doesn't need
to know or care whether it's rendering real or demo data.

Deliberately includes: two platforms (ECS + EKS), four environments, a
service with desired != running (to show the drift indicator), and one
EKS cluster with a discovery warning (to show graceful degradation).
"""

import datetime


def _commit(sha, message, author, days_ago, jira=None):
    date = (datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')
    result = {
        'sha': sha, 'short_sha': sha[:7],
        'url': f'https://github.com/example-org/example-repo/commit/{sha}',
        'message': message, 'author': author, 'date': date, 'verified': True,
    }
    if jira:
        result['jira'] = jira
    return result


def attach_demo_enrichment(clusters, start_time, end_time):
    """Bolt on fake Harness executions + New Relic markers for the demo,
    shaped like enrichment.py's real output, so --demo --mode history
    shows what those sections look like."""
    span = (end_time - start_time).total_seconds()

    def at(frac):
        return start_time + datetime.timedelta(seconds=span * frac)

    for cluster in clusters:
        for service in cluster.get('services', []):
            if cluster['name'] == 'payments-prod' and service['name'] == 'payments-api':
                service['harness_executions'] = [
                    {
                        'pipeline_name': 'payments-api-deploy',
                        'status': 'SUCCESS',
                        'started_at': at(0.78),
                        'artifact_versions': ['payments-api:9f8e7d6'],
                        'triggered_by': 'ci-pipeline-bot',
                        'execution_url': 'https://app.harness.io/ng/account/example/cd/orgs/default/projects/payments/pipelines/payments_api_deploy/executions/abc123/pipeline',
                    },
                    {
                        'pipeline_name': 'payments-api-deploy',
                        'status': 'SUCCESS',
                        'started_at': at(0.40),
                        'artifact_versions': ['payments-api:2f1e0d9'],
                        'triggered_by': 'priya.n',
                        'execution_url': 'https://app.harness.io/ng/account/example/cd/orgs/default/projects/payments/pipelines/payments_api_deploy/executions/def456/pipeline',
                    },
                ]
                service['newrelic_markers'] = [
                    {
                        'timestamp': at(0.785),
                        'version': '9f8e7d6',
                        'user': 'ci-pipeline-bot',
                        'deep_link': 'https://one.newrelic.com/changes-and-releases',
                        'deployment_id': 'demo-deploy-2',
                    },
                    {
                        'timestamp': at(0.405),
                        'version': '2f1e0d9',
                        'user': 'priya.n',
                        'deep_link': 'https://one.newrelic.com/changes-and-releases',
                        'deployment_id': 'demo-deploy-1',
                    },
                ]
    return clusters


def get_demo_history_clusters(start_time, end_time, is_present_scan=True):
    """Fake version-timeline data, shaped like discovery/ecs_history.py and
    discovery/eks_history.py output, spread proportionally across whatever
    [start_time, end_time] window was requested."""
    span = (end_time - start_time).total_seconds()

    def at(frac):
        return start_time + datetime.timedelta(seconds=span * frac)

    def make_leg(frac, tag, sha, message, author):
        return {
            'start': at(frac),
            'containers': [{
                'name': 'app',
                'image': f'111111111111.dkr.ecr.us-east-1.amazonaws.com/payments-api:{tag}',
                'tag': tag,
                'commit': _commit(sha, message, author, 1),
            }],
        }

    def finalize(legs):
        legs.sort(key=lambda l: l['start'])
        for idx, leg in enumerate(legs):
            leg['end'] = legs[idx + 1]['start'] if idx + 1 < len(legs) else None
            leg['current'] = (idx == len(legs) - 1) and is_present_scan
        return legs

    payments_prod_timeline = finalize([
        make_leg(0.05, '7c6b5a4', '7c6b5a4d3e2f1091827364554637281910abcde',
                 'Add fraud-score threshold config', 'Priya N.'),
        make_leg(0.40, '2f1e0d9', '2f1e0d9c8b7a695041322130f0e0d0c0b0a0908',
                 'Migrate to new card-network SDK', 'Priya N.'),
        make_leg(0.78, '9f8e7d6', '9f8e7d6c5b4a3921807f6e5d4c3b2a1908f7e6d5',
                 'TEAM-2091: Bump retry backoff for card-network timeouts', 'Priya N.'),
    ])
    payments_prod_timeline[-1]['containers'][0]['commit']['jira'] = [{
        'key': 'TEAM-2091', 'url': 'https://example.atlassian.net/browse/TEAM-2091',
        'summary': 'Bump retry backoff for card-network timeouts', 'status': 'Done',
    }]
    payments_prod_timeline[-1]['containers'][0]['nexus'] = {
        'asset_url': 'https://nexus.example.com/repository/team-images/v2/payments-api/manifests/9f8e7d6',
        'browse_url': 'https://nexus.example.com/#browse/browse:team-images',
        'base_image': {'name': 'nexus.example.com/base-images/python:3.11-slim', 'digest': None},
    }

    checkout_qa_timeline = finalize([
        make_leg(0.15, 'v2.1.0-g1122334', '11223344556677889900aabbccddeeff00112233',
                 'Initial split-tender support', 'Marcus T.'),
        make_leg(0.60, 'v2.3.0-g4c5d6e7', '4c5d6e7f8a9b0123c4d5e6f7a8b9c0d1e2f3a4b5',
                 'Fix currency rounding on split-tender orders', 'Marcus T.'),
    ])

    # A quiet service: nothing changed inside the window -- only the
    # "boundary" revision carried in from just before it. This is what
    # "no changes in range" looks like in the report.
    auth_timeline = finalize([
        make_leg(-0.05, 'build-410-8899aab', '8899aabbccddeeff0011223344556677889900aa',
                 'Add refresh-token rotation', 'Dana W.'),
    ])

    return [
        {
            'platform': 'ECS', 'name': 'payments-prod', 'region': 'us-east-1',
            'team': 'Payments', 'environment': 'production',
            'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/payments-prod/services?region=us-east-1',
            'services': [{
                'name': 'payments-api',
                'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/payments-prod/services/payments-api/health?region=us-east-1',
                'timeline': payments_prod_timeline,
            }],
        },
        {
            'platform': 'EKS', 'name': 'checkout-qa', 'region': 'us-west-2',
            'team': 'Checkout', 'environment': 'qa',
            'console_url': 'https://us-west-2.console.aws.amazon.com/eks/home?region=us-west-2#/clusters/checkout-qa',
            'services': [{
                'name': 'checkout/cart-service',
                'console_url': None,
                'timeline': checkout_qa_timeline,
            }],
        },
        {
            'platform': 'ECS', 'name': 'platform-systest', 'region': 'us-east-1',
            'team': 'Platform', 'environment': 'systest',
            'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/platform-systest/services?region=us-east-1',
            'services': [{
                'name': 'auth-service',
                'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/platform-systest/services/auth-service/health?region=us-east-1',
                'timeline': auth_timeline,
                'warning': None,
            }],
        },
    ]


def get_demo_team_repos():
    """Fake team -> repos registry, tuned to show both kinds of coverage
    gap in the demo: Payments has a registered repo never seen deployed;
    Checkout has a deployed repo that isn't in the registry; Platform is
    fully covered."""
    return {
        'Payments': ['example-org/payments-api', 'example-org/payments-worker'],
        'Checkout': ['example-org/checkout-web'],
        'Platform': ['example-org/auth-service'],
    }


def get_demo_clusters():
    return [
        {
            'platform': 'ECS', 'name': 'payments-dev', 'region': 'us-east-1',
            'team': 'Payments', 'environment': 'dev',
            'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/payments-dev/services?region=us-east-1',
            'services': [{
                'name': 'payments-api', 'desired_count': 2, 'running_count': 2,
                'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/payments-dev/services/payments-api/health?region=us-east-1',
                'containers': [{
                    'name': 'app', 'image': '111111111111.dkr.ecr.us-east-1.amazonaws.com/payments-api:a1b2c3d',
                    'tag': 'a1b2c3d', 'github_repo': 'example-org/payments-api',
                    'commit': _commit('a1b2c3d4e5f60718293a4b5c6d7e8f9012345678',
                                       'TEAM-1856: Add idempotency key support to charge endpoint', 'Priya N.', 1,
                                       jira=[{'key': 'TEAM-1856', 'url': 'https://example.atlassian.net/browse/TEAM-1856',
                                              'summary': 'Add idempotency key support to charge endpoint', 'status': 'Done'}]),
                    'nexus': {
                        'asset_url': 'https://nexus.example.com/repository/team-images/v2/payments-api/manifests/a1b2c3d',
                        'browse_url': 'https://nexus.example.com/#browse/browse:team-images',
                        'base_image': {'name': 'nexus.example.com/base-images/python:3.11-slim', 'digest': None},
                    },
                }],
            }],
        },
        {
            'platform': 'ECS', 'name': 'payments-prod', 'region': 'us-east-1',
            'team': 'Payments', 'environment': 'production',
            'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/payments-prod/services?region=us-east-1',
            'services': [{
                'name': 'payments-api', 'desired_count': 6, 'running_count': 4,
                'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/payments-prod/services/payments-api/health?region=us-east-1',
                'containers': [{
                    'name': 'app', 'image': '111111111111.dkr.ecr.us-east-1.amazonaws.com/payments-api:9f8e7d6',
                    'tag': '9f8e7d6', 'github_repo': 'example-org/payments-api',
                    'commit': _commit('9f8e7d6c5b4a3921807f6e5d4c3b2a1908f7e6d5',
                                       'Bump retry backoff for card-network timeouts', 'Priya N.', 6),
                }],
            }],
        },
        {
            'platform': 'EKS', 'name': 'checkout-qa', 'region': 'us-west-2',
            'team': 'Checkout', 'environment': 'qa',
            'console_url': 'https://us-west-2.console.aws.amazon.com/eks/home?region=us-west-2#/clusters/checkout-qa',
            'services': [{
                'name': 'checkout/cart-service', 'desired_count': 3, 'running_count': 3,
                'console_url': None,
                'containers': [{
                    'name': 'cart-service', 'image': '111111111111.dkr.ecr.us-west-2.amazonaws.com/cart-service:v2.3.0-g4c5d6e7',
                    'tag': 'v2.3.0-g4c5d6e7', 'github_repo': 'example-org/cart-service',
                    'commit': _commit('4c5d6e7f8a9b0123c4d5e6f7a8b9c0d1e2f3a4b5',
                                       'Fix currency rounding on split-tender orders', 'Marcus T.', 2),
                }],
            }],
        },
        {
            'platform': 'EKS', 'name': 'checkout-prod', 'region': 'us-west-2',
            'team': 'Checkout', 'environment': 'production',
            'console_url': 'https://us-west-2.console.aws.amazon.com/eks/home?region=us-west-2#/clusters/checkout-prod',
            'warning': 'could not list deployments in checkout-prod (check aws-auth / access entries): Unauthorized',
            'services': [],
        },
        {
            'platform': 'ECS', 'name': 'platform-systest', 'region': 'us-east-1',
            'team': 'Platform', 'environment': 'systest',
            'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/platform-systest/services?region=us-east-1',
            'services': [{
                'name': 'auth-service', 'desired_count': 1, 'running_count': 1,
                'console_url': 'https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/platform-systest/services/auth-service/health?region=us-east-1',
                'containers': [{
                    'name': 'app', 'image': '111111111111.dkr.ecr.us-east-1.amazonaws.com/auth-service:build-482-1a2b3c4',
                    'tag': 'build-482-1a2b3c4', 'github_repo': 'example-org/auth-service',
                    'commit': _commit('1a2b3c4d5e6f7081920a3b4c5d6e7f8091a2b3c4',
                                       'Rotate signing keys on a 24h schedule', 'Dana W.', 4),
                }],
            }],
        },
    ]
