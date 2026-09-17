/* eslint-disable */
// GENERATED from contracts/openapi.yaml (contracts-v1.0.0). Do not edit.
// Regenerate: npm run gen:api. CI/local check: npm run check:api.

export interface paths {
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getHealth */
        get: operations["getHealth"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** listPlots */
        get: operations["listPlots"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plots/{plot_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getPlot */
        get: operations["getPlot"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plots/{plot_id}/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * startVerification
         * @description Только demo-актор issuer. Неверная роль — 403.
         */
        post: operations["startVerification"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getVerificationJob */
        get: operations["getVerificationJob"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/verifications/{verification_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getVerification */
        get: operations["getVerification"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/verifications/{verification_id}/proof": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getProof */
        get: operations["getProof"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/verifications/{verification_id}/canonical": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * getCanonicalEvidence
         * @description Возвращает сохранённые JCS-байты без повторной сериализации.
         */
        get: operations["getCanonicalEvidence"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plots/{plot_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getHistory */
        get: operations["getHistory"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plots/{plot_id}/credits": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getCredits */
        get: operations["getCredits"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plots/{plot_id}/issue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * issueBatch
         * @description Только demo-актор issuer. Неверная роль — 403.
         */
        post: operations["issueBatch"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/batches/{batch_id}/buy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** buyCredits */
        post: operations["buyCredits"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/batches/{batch_id}/transfer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** transferCredits */
        post: operations["transferCredits"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/operations/{operation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getOperation */
        get: operations["getOperation"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** listEvents */
        get: operations["listEvents"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** getArtifact */
        get: operations["getArtifact"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        EvidenceHash32: string;
        /** Format: date-time */
        EvidenceTimestamp: string;
        EvidenceSourceAsset: {
            /** @enum {string} */
            band: "B04" | "B08" | "B8A" | "B12" | "SCL";
            source_ref: string;
            local_sha256: string;
            scale_applied: number;
            offset_applied: number;
            /** @enum {string} */
            transform_origin: "PRODUCT_METADATA" | "PROVIDER_HARMONIZED";
        };
        EvidenceScene: {
            scene_id: string;
            /** Format: date-time */
            acquired_at: string;
            provider: string;
            collection: string;
            processing_baseline: string | null;
            mgrs_tile: string | null;
            assets: components["schemas"]["EvidenceSourceAsset"][];
        };
        EvidenceGrid: {
            epsg: number;
            /** @constant */
            resolution_m: 20;
            width: number;
            height: number;
            transform: number[];
        };
        EvidenceForestMask: {
            source: string;
            version: string;
            reference_year: number;
            sha256: string;
            interpretation_note: string;
        };
        EvidenceParameters: {
            /** @constant */
            ndvi_bands: [
                "B08",
                "B04"
            ];
            /** @constant */
            nbr_bands: [
                "B8A",
                "B12"
            ];
            /** @constant */
            disturbance_dnbr_min: 0.27;
            /** @constant */
            min_component_area_ha: 1;
            /** @constant */
            connectivity: 8;
            /** @constant */
            excluded_scl_classes: [
                0,
                1,
                2,
                3,
                6,
                7,
                8,
                9,
                10,
                11
            ];
            /** @constant */
            resampling_continuous: "average";
            /** @constant */
            resampling_categorical: "nearest";
        };
        EvidenceMethod: {
            pipeline_version: string;
            code_commit: string | null;
            config_sha256: string;
            grid: components["schemas"]["EvidenceGrid"] | null;
            forest_mask: components["schemas"]["EvidenceForestMask"] | null;
            parameters: components["schemas"]["EvidenceParameters"];
        };
        EvidenceQuality: {
            paired_valid_aoi_ratio: number | null;
            paired_valid_forest_ratio: number | null;
            aoi_cloud_ratio_before: number | null;
            aoi_cloud_ratio_after: number | null;
            metadata_complete: boolean;
            grid_aligned: boolean;
            /** @enum {string} */
            temporal_comparability: "YES" | "NO" | "UNCERTAIN";
            temporal_note: string;
        };
        EvidenceMetrics: {
            plot_area_ha: number;
            baseline_forest_area_ha: number | null;
            analysed_forest_area_ha: number | null;
            affected_area_ha: number | null;
            affected_fraction_of_baseline_forest: number | null;
            ndvi_before_mean: number | null;
            ndvi_after_mean: number | null;
            dnbr_mean: number | null;
            /** @constant */
            dnbr_mean_scope: "PAIRED_VALID_BASELINE_FOREST";
            baseline_forest_pixel_count: number | null;
            paired_valid_forest_pixel_count: number | null;
            affected_pixel_count: number | null;
        };
        EvidenceFirms: {
            /** @enum {string} */
            support: "SUPPORTED" | "NOT_FOUND" | "NOT_CHECKED";
            hotspot_count: number;
            /** Format: date-time */
            window_start: string;
            /** Format: date-time */
            window_end: string;
            /** @constant */
            spatial_tolerance_m: 500;
            product: string;
            confidence_filter: string[];
            source_refs: string[];
            matched_points_artifact_id: string | null;
        };
        EvidenceArtifact: {
            artifact_id: string;
            /** @enum {string} */
            role: "PREVIEW_BEFORE" | "PREVIEW_AFTER" | "DNBR_RASTER" | "AFFECTED_AREA" | "FIRMS_POINTS" | "DNBR_PREVIEW" | "SWIR_BEFORE" | "SWIR_AFTER";
            relative_path: string;
            /** @enum {string} */
            media_type: "image/png" | "image/webp" | "image/tiff" | "application/geo+json";
            sha256: string;
            size_bytes: number;
            bounds_wgs84?: [
                number,
                number,
                number,
                number
            ];
            width?: number;
            height?: number;
        } & unknown;
        /** VerificationEvidence */
        VerificationEvidence: {
            /** @constant */
            schema_version: "1.0.0";
            /** @enum {string} */
            dataset_kind: "REAL" | "SYNTHETIC";
            plot_id: string;
            plot_geometry_hash: string;
            observation: {
                before: components["schemas"]["EvidenceScene"];
                after: components["schemas"]["EvidenceScene"];
            };
            /** @enum {string} */
            outcome: "NO_CHANGE" | "DISTURBANCE_DETECTED" | "INSUFFICIENT_DATA";
            method: components["schemas"]["EvidenceMethod"];
            quality: components["schemas"]["EvidenceQuality"];
            metrics: components["schemas"]["EvidenceMetrics"];
            firms: components["schemas"]["EvidenceFirms"];
            artifacts: components["schemas"]["EvidenceArtifact"][];
            limitations: string[];
        } & (unknown & unknown & unknown);
        ErrorDetail: {
            code: string;
            message: string;
            details: {
                [key: string]: unknown;
            };
        };
        Error: {
            error: components["schemas"]["ErrorDetail"];
            /** Format: uuid */
            request_id: string;
        };
        ArtifactLink: {
            artifact_id: string;
            /** @enum {string} */
            role: "PREVIEW_BEFORE" | "PREVIEW_AFTER" | "DNBR_RASTER" | "AFFECTED_AREA" | "FIRMS_POINTS" | "DNBR_PREVIEW" | "SWIR_BEFORE" | "SWIR_AFTER";
            url: string;
            sha256: string;
            media_type: string;
        };
        DecisionRecord: {
            evidence_hash: string;
            plot_id: string;
            /** @constant */
            policy_version: "1.0.0";
            policy_parameters_hash: string;
            /** @enum {string} */
            decision: "NO_RESTRICTION" | "REVIEW_REQUIRED" | "FREEZE_REQUESTED";
            /** @enum {string} */
            reason: "NO_SIGNIFICANT_CHANGE" | "DATA_INSUFFICIENT" | "DATA_REVIEW" | "DISTURBANCE_UNATTRIBUTED" | "BELOW_POLICY_THRESHOLD" | "FIRE_REVERSAL";
            /** Format: date-time */
            effective_observed_at: string;
            /** Format: date-time */
            replay_as_of: string;
        };
        Verification: {
            /** Format: uuid */
            verification_id: string;
            evidence: components["schemas"]["VerificationEvidence"];
            evidence_hash: string;
            /** @enum {string} */
            evidence_quality: "SUFFICIENT" | "REVIEW_REQUIRED" | "INSUFFICIENT";
            evidence_quality_score: number | null;
            /** @enum {string} */
            decision: "NO_RESTRICTION" | "REVIEW_REQUIRED" | "FREEZE_REQUESTED";
            /** @enum {string} */
            reason: "NO_SIGNIFICANT_CHANGE" | "DATA_INSUFFICIENT" | "DATA_REVIEW" | "DISTURBANCE_UNATTRIBUTED" | "BELOW_POLICY_THRESHOLD" | "FIRE_REVERSAL";
            decision_record: components["schemas"]["DecisionRecord"];
            decision_hash: string;
            is_latest: boolean;
            /** Format: date-time */
            processed_at: string;
            /** @constant */
            observation_mode: "HISTORICAL_REPLAY";
            /** @enum {string} */
            computation_mode: "COMPUTED" | "CACHED_REPLAY";
            artifacts: components["schemas"]["ArtifactLink"][];
        };
        JobAccepted: {
            /** Format: uuid */
            job_id: string;
            /** @constant */
            state: "QUEUED";
            status_url: string;
        };
        Job: {
            /** Format: uuid */
            job_id: string;
            /** @enum {string} */
            state: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
            verification_id: string | null;
            error: components["schemas"]["ErrorDetail"] | null;
        } & (unknown & unknown);
        Receipt: {
            transaction_hash: string;
            block_number: string;
            /** @constant */
            status: 1;
            event_names: string[];
            /** @constant */
            state_readback_ok: true;
        };
        OperationAccepted: {
            /** Format: uuid */
            operation_id: string;
            /** @constant */
            transaction_state: "QUEUED";
            status_url: string;
        };
        Operation: {
            /** Format: uuid */
            operation_id: string;
            /** @enum {string} */
            kind: "ISSUE" | "BUY" | "TRANSFER" | "FREEZE";
            /** @enum {string} */
            transaction_state: "QUEUED" | "SUBMITTED" | "CONFIRMED" | "FAILED";
            tx_hash: string | null;
            batch_id: string | null;
            error: components["schemas"]["ErrorDetail"] | null;
            receipt: components["schemas"]["Receipt"] | null;
        } & (unknown & unknown);
        CreditBatch: {
            batch_id: string;
            plot_id: string;
            seller: string;
            /** @enum {string} */
            actor: "issuer" | "buyer" | "recipient";
            total_supply: string;
            seller_balance: string;
            actor_balance: string;
            unit_price_wei: string;
            /** @enum {string} */
            credit_status: "ACTIVE" | "FROZEN" | "REVOKED";
            evidence_hash: string;
            decision_hash: string;
            /** Format: date-time */
            issued_at: string;
            frozen_at: string | null;
            /** Format: date-time */
            last_observed_at: string;
            /** Format: date-time */
            chain_state_checked_at: string;
            can_buy: boolean;
            can_transfer_backend: boolean;
        };
        PlotSummary: {
            plot_id: string;
            name: string;
            latest_verification_id: string | null;
            evidence_quality: ("SUFFICIENT" | "REVIEW_REQUIRED" | "INSUFFICIENT") | null;
            latest_decision: ("NO_RESTRICTION" | "REVIEW_REQUIRED" | "FREEZE_REQUESTED") | null;
        };
        Plot: {
            plot_id: string;
            name: string;
            latest_verification_id: string | null;
            evidence_quality: ("SUFFICIENT" | "REVIEW_REQUIRED" | "INSUFFICIENT") | null;
            latest_decision: ("NO_RESTRICTION" | "REVIEW_REQUIRED" | "FREEZE_REQUESTED") | null;
            geometry: {
                /** @constant */
                type: "Polygon";
                coordinates: [
                    number,
                    number
                ][][];
            } | {
                /** @constant */
                type: "MultiPolygon";
                coordinates: [
                    number,
                    number
                ][][][];
            };
            geometry_hash: string;
            area_ha: number;
            can_issue: boolean;
            can_buy: boolean;
            can_transfer_backend: boolean;
            action_block_reason: string | null;
        };
        HistoryItem: {
            /** Format: uuid */
            verification_id: string;
            /** Format: date-time */
            observed_at: string;
            /** Format: date-time */
            processed_at: string;
            /** @enum {string} */
            outcome: "NO_CHANGE" | "DISTURBANCE_DETECTED" | "INSUFFICIENT_DATA";
            /** @enum {string} */
            evidence_quality: "SUFFICIENT" | "REVIEW_REQUIRED" | "INSUFFICIENT";
            /** @enum {string} */
            decision: "NO_RESTRICTION" | "REVIEW_REQUIRED" | "FREEZE_REQUESTED";
            is_latest: boolean;
        };
        Anchor: {
            /** @enum {string} */
            event_name: "Issued" | "Frozen";
            batch_id: string;
            tx_hash: string;
            evidence_hash: string;
            decision_hash: string | null;
            /** @constant */
            confirmed: true;
        };
        Proof: {
            evidence_hash: string;
            recomputed_hash: string;
            decision_hash: string;
            canonical_url: string;
            anchors: components["schemas"]["Anchor"][];
            integrity_ok: boolean;
        };
        Event: {
            /** Format: uuid */
            event_id: string;
            /** Format: date-time */
            occurred_at: string;
            plot_id: string;
            /** @enum {string} */
            kind: "VERIFICATION" | "DECISION" | "TX_SUBMITTED" | "TX_CONFIRMED" | "TX_FAILED";
            verification_id: string | null;
            operation_id: string | null;
            tx_hash: string | null;
            batch_id: string | null;
            message: string;
        };
        Events: {
            items: components["schemas"]["Event"][];
            next_cursor: string | null;
        };
        Health: {
            /** @enum {string} */
            api: "UP" | "DOWN";
            /** @enum {string} */
            db: "UP" | "DOWN";
            /** @enum {string} */
            worker: "UP" | "DOWN";
            /** @enum {string} */
            chain: "UP" | "DOWN";
            deployment_id: string | null;
            /** @enum {string} */
            mode: "CONTRACT_FIXTURE" | "LOCAL_DEMO";
        };
        VerifyRequest: {
            /** @enum {string} */
            scenario_id: "baseline" | "post_fire" | "insufficient";
        };
        IssueRequest: {
            demo_authorization_id: string;
        };
        BuyRequest: {
            amount: string;
        };
        TransferRequest: {
            /** @enum {string} */
            to_actor: "issuer" | "buyer" | "recipient";
            amount: string;
        };
        Plots: {
            items: components["schemas"]["PlotSummary"][];
        };
        Credits: {
            items: components["schemas"]["CreditBatch"][];
        };
        History: {
            items: components["schemas"]["HistoryItem"][];
        };
    };
    responses: {
        /** @description Структурированная ошибка */
        Failure: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
    };
    parameters: {
        IdempotencyKey: string;
        DemoActor: "issuer" | "buyer" | "recipient";
    };
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    getHealth: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    listPlots: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Plots"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getPlot: {
        parameters: {
            query?: never;
            header: {
                "X-Demo-Actor": components["parameters"]["DemoActor"];
            };
            path: {
                plot_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Plot"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    startVerification: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
                "X-Demo-Actor": components["parameters"]["DemoActor"];
            };
            path: {
                plot_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VerifyRequest"];
            };
        };
        responses: {
            /** @description Принято в очередь */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobAccepted"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getVerificationJob: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Job"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getVerification: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                verification_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Verification"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getProof: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                verification_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Proof"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getCanonicalEvidence: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                verification_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationEvidence"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getHistory: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plot_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["History"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getCredits: {
        parameters: {
            query?: never;
            header: {
                "X-Demo-Actor": components["parameters"]["DemoActor"];
            };
            path: {
                plot_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Credits"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    issueBatch: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
                "X-Demo-Actor": components["parameters"]["DemoActor"];
            };
            path: {
                plot_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IssueRequest"];
            };
        };
        responses: {
            /** @description Принято в очередь */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OperationAccepted"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    buyCredits: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
                "X-Demo-Actor": components["parameters"]["DemoActor"];
            };
            path: {
                batch_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BuyRequest"];
            };
        };
        responses: {
            /** @description Принято в очередь */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OperationAccepted"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    transferCredits: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
                "X-Demo-Actor": components["parameters"]["DemoActor"];
            };
            path: {
                batch_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TransferRequest"];
            };
        };
        responses: {
            /** @description Принято в очередь */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OperationAccepted"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getOperation: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Operation"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    listEvents: {
        parameters: {
            query: {
                plot_id: string;
                cursor?: string;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Успешное чтение */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Events"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getArtifact: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                artifact_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Файл из разрешённого manifest */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "image/png": string;
                    "image/webp": string;
                    "image/tiff": string;
                    "application/geo+json": string;
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
}
