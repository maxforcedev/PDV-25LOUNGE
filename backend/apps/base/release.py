import logging

from django.conf import settings


def release_metadata():
    return {
        'version': settings.APP_VERSION,
        'commit': settings.GIT_SHA,
        'environment': settings.ENVIRONMENT,
        'build_date': settings.BUILD_DATE,
    }


def log_release_metadata():
    metadata = release_metadata()
    logging.getLogger('django').info(
        'CORE PDV startup: version=%s environment=%s commit=%s build_date=%s',
        metadata['version'],
        metadata['environment'],
        metadata['commit'],
        metadata['build_date'],
    )
