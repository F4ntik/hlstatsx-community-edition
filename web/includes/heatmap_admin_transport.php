<?php

declare(strict_types=1);

const HEATMAP_ADMIN_MAX_TRANSPORT_BYTES = 22020096;

function heatmap_admin_request_content_length(array $server): ?int
{
    $rawLength = $server['CONTENT_LENGTH'] ?? null;
    if (is_int($rawLength)) {
        return $rawLength >= 0 ? $rawLength : null;
    }
    if (!is_string($rawLength) || preg_match('/^[0-9]+$/D', $rawLength) !== 1) {
        return null;
    }

    $length = intval($rawLength);
    return $length >= 0 ? $length : null;
}

function heatmap_admin_request_exceeds_transport_limit(array $server): bool
{
    if (strtoupper(strval($server['REQUEST_METHOD'] ?? 'GET')) !== 'POST') {
        return false;
    }

    $length = heatmap_admin_request_content_length($server);
    return $length !== null && $length > HEATMAP_ADMIN_MAX_TRANSPORT_BYTES;
}

function heatmap_admin_reject_oversize_post(array $server): bool
{
    if (!heatmap_admin_request_exceeds_transport_limit($server)) {
        return false;
    }

    http_response_code(413);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode(array(
        'ok' => false,
        'code' => 'invalid_request',
        'message' => 'The calibration request is invalid.',
    ), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);

    return true;
}
