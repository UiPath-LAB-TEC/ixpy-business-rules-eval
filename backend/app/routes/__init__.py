from . import analytics, annotations, dashboard, documents, evaluations, exports, health, logs, reviews, runs, training_exceptions


routers = [
    health.router,
    runs.router,
    dashboard.router,
    documents.router,
    evaluations.router,
    logs.router,
    analytics.router,
    reviews.router,
    exports.router,
    training_exceptions.router,
    annotations.router,
]
