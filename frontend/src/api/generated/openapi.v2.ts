/* eslint-disable */
// GENERATED from contracts/v2/openapi.v2.yaml. Do not edit.
// Regenerate: npm run gen:api. CI/local check: npm run check:api.

export interface paths {
    "/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Exchange a username and a password for an opaque session token
         * @description The token is cryptographically random, is stored on the server only as a
         *     hash, and is not derived from anything present in a client build. It goes
         *     back in the response body, not in a cookie, so the client can keep it in
         *     memory and it is never replayed by the browser on its own.
         *
         *     A wrong username and a wrong password give the same 401 with the same
         *     message, because telling them apart tells an attacker which usernames
         *     exist. Repeated failures for one username are rate limited with 429.
         *
         *     There is no refresh token and no silent restoration. A reload signs the
         *     person in again; the alternative would be a secret that survives the
         *     page, which is the thing this design is avoiding.
         */
        post: operations["login"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/demo-accounts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Demonstration accounts this deployment turned on, if any
         * @description A deployment that wants a one-click walkthrough declares demonstration
         *     accounts; everywhere else this returns an empty list, and then one-click
         *     entry does not exist. No password is ever returned: the client learns
         *     which roles it may enter, not how to enter them.
         *
         *     The list is public on purpose. It says nothing an attacker can use: these
         *     accounts exist only where somebody deliberately enabled them, and the
         *     passwords behind them live in the environment of the service.
         */
        get: operations["demoAccounts"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/demo-login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Enter a configured demonstration account without typing its password
         * @description For a walkthrough where a person should click a role rather than retype a
         *     password that is not a secret to them anyway. The service resolves the
         *     password from its own environment, so the browser never holds it and a
         *     build cannot carry it.
         *
         *     An account that this deployment did not declare is 404, whether or not a
         *     user row with that name exists: the answer describes the demonstration
         *     configuration, not the user table. The session it returns is an ordinary
         *     session — same token shape, same expiry, same audit record — because a
         *     demonstration that behaved differently from the real thing would not be
         *     a demonstration of it.
         */
        post: operations["demoLogin"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** The signed-in person and the role the server holds for them */
        get: operations["whoAmI"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Revoke this session immediately
         * @description Needs the session it is revoking, so that the sign-out can be recorded
         *     against the person who performed it. The token cannot be used again
         *     afterwards, which means a second call with the same token is 401: the
         *     session it names no longer exists. A client that has already been
         *     signed out has nothing left to do.
         */
        post: operations["logout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Supplied areas, sample requests, available years and method versions */
        get: operations["getCatalog"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/areas/measure": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Geodesic area of a contour, before anything is queued
         * @description Answers "how big is this, and may I submit it" without creating an
         *     analysis. It normalizes the contour and measures it with the same
         *     geodesic algorithm the analysis path uses, so a measurement can never
         *     disagree with the run that follows.
         *
         *     A contour that cannot be used is a 200 with valid=false and named
         *     errors; 422 is reserved for a body that is not a GeoJSON geometry at
         *     all. Exceeding max_area_ha sets within_limit=false and is reported, not
         *     thrown.
         */
        post: operations["measureArea"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * The requests this role is allowed to see
         * @description An owner sees their own. A verifier sees all of them, because reviewing
         *     them is the job. An investor sees only the finalized ones: a draft is
         *     not a finding.
         */
        get: operations["listRequests"];
        put?: never;
        /**
         * Start a verification request as a draft
         * @description A request is the thing a person works with: a contour, a period and an
         *     optional stated volume, followed from a draft to a finalized passport.
         *     It starts as DRAFT and nothing is calculated yet.
         */
        post: operations["createRequest"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** One request with its recorded history */
        get: operations["getRequest"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Change the stated volume while the request is still a draft
         * @description Only the owner, and only in DRAFT. The contour and the period are not
         *     editable: changing those is a different request, and a claim compared
         *     against a different scope is not a comparison.
         */
        patch: operations["updateRequest"];
        trace?: never;
    };
    "/requests/{request_id}/submit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Hand a draft over for verification */
        post: operations["submitRequest"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/analysis": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Queue the calculation for a submitted request
         * @description Moves the request to ANALYSING and queues the analysis with the
         *     contour, period and claim the request holds. A run that fails returns
         *     the request to SUBMITTED so it can be tried again; it never advances.
         */
        post: operations["runRequestAnalysis"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/finalize": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * A verifier pins this passport version as the finalized one
         * @description Only a verifier, and only from CALCULATED. Finalizing does not change
         *     Q, the interval, the claim comparison or anything else the calculation
         *     produced: it records that a named person accepted a particular passport
         *     content hash at a particular time. A later recalculation produces a new
         *     passport and leaves this record intact.
         *
         *     A result whose q is null may be finalized. "We could not tell" is a
         *     legitimate verified outcome, and the passport says so; what it may not
         *     do is turn into units.
         */
        post: operations["finalizeRequest"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/demo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * The demonstration state of this request
         * @description A demonstration of what a unit lifecycle would look like, performed by
         *     the anyone who may see the request. Nothing here exists in a registry and none of it confers a
         *     right to a carbon unit; is_demonstration is always true and the note
         *     says so in words a reader cannot miss.
         *
         *     Issuing needs a passport a verifier has finalized and a positive q.
         *     Zero and null both refuse with 409 NO_POSITIVE_UNITS: every real plot
         *     in the supplied data comes out at zero, so a demonstration that quietly
         *     issued nothing would be the one misleading thing in the tool.
         *
         *     Every transition is idempotent: repeating one returns the state that
         *     already exists rather than recording a second.
         */
        get: operations["getDemoUnit"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/demo/issue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * An owner issues demonstration units
         * @description A demonstration of what a unit lifecycle would look like, performed by
         *     the owner. Nothing here exists in a registry and none of it confers a
         *     right to a carbon unit; is_demonstration is always true and the note
         *     says so in words a reader cannot miss.
         *
         *     Issuing needs a passport a verifier has finalized and a positive q.
         *     Zero and null both refuse with 409 NO_POSITIVE_UNITS: every real plot
         *     in the supplied data comes out at zero, so a demonstration that quietly
         *     issued nothing would be the one misleading thing in the tool.
         *
         *     Every transition is idempotent: repeating one returns the state that
         *     already exists rather than recording a second.
         */
        post: operations["issueDemoUnit"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/demo/transfer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * An investor accepts the demonstration transfer
         * @description A demonstration of what a unit lifecycle would look like, performed by
         *     the investor. Nothing here exists in a registry and none of it confers a
         *     right to a carbon unit; is_demonstration is always true and the note
         *     says so in words a reader cannot miss.
         *
         *     Issuing needs a passport a verifier has finalized and a positive q.
         *     Zero and null both refuse with 409 NO_POSITIVE_UNITS: every real plot
         *     in the supplied data comes out at zero, so a demonstration that quietly
         *     issued nothing would be the one misleading thing in the tool.
         *
         *     Every transition is idempotent: repeating one returns the state that
         *     already exists rather than recording a second.
         */
        post: operations["acceptDemoTransfer"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/demo/retire": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * The holder retires the demonstration units
         * @description A demonstration of what a unit lifecycle would look like, performed by
         *     the holder. Nothing here exists in a registry and none of it confers a
         *     right to a carbon unit; is_demonstration is always true and the note
         *     says so in words a reader cannot miss.
         *
         *     Issuing needs a passport a verifier has finalized and a positive q.
         *     Zero and null both refuse with 409 NO_POSITIVE_UNITS: every real plot
         *     in the supplied data comes out at zero, so a demonstration that quietly
         *     issued nothing would be the one misleading thing in the tool.
         *
         *     Every transition is idempotent: repeating one returns the state that
         *     already exists rather than recording a second.
         */
        post: operations["retireDemoUnit"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analyses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Queue an analysis of one contour over one period
         * @description Accepts either a geometry or the identifier of a supplied area. Naming a
         *     supplied area is a shortcut for pasting its polygon and changes nothing
         *     else about the analysis.
         *
         *     The request is bound to (caller, operation, Idempotency-Key) together
         *     with the canonical hash of the normalized request. The same key with the
         *     same request replays the stored 202; the same key with a different
         *     request is 409 IDEMPOTENCY_CONFLICT. The caller is taken from the
         *     authenticated session, never from a client-supplied role header.
         *
         *     An optional claimed_units is an input label. It enters the request
         *     identity, and it never changes the calculated numbers.
         */
        post: operations["createAnalysis"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analyses/{analysis_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Job progress and, once SUCCEEDED, the typed result */
        get: operations["getAnalysis"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analyses/{analysis_id}/artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * One manifest-listed artifact of this analysis
         * @description Only artifacts listed in the manifest of this analysis are served, and
         *     only after their stored bytes match the recorded sha256 and size. A
         *     mismatch is 503 ARTIFACT_INTEGRITY_FAILED, never a silently different
         *     file.
         */
        get: operations["getAnalysisArtifact"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analyses/{analysis_id}/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * The passport as JSON or as a self-contained HTML document
         * @description The HTML report is self-contained: it embeds the numbers it shows and
         *     does not depend on a session URL that expires, so an archived copy still
         *     reads correctly. Both formats carry exactly the values of the result.
         */
        get: operations["getAnalysisReport"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analyses/{analysis_id}/value": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * q multiplied by each price, with an optional price of the caller's own
         * @description Nothing here is stored and no hash moves. A price the caller supplies
         *     is an input, not a quotation this system stands behind: it comes back
         *     labelled USER_SCENARIO and is deliberately kept out of the analysis,
         *     because a stated price must never be able to change a passport.
         *
         *     When q is null every value is null. There is no scenario value for an
         *     answer that does not exist.
         */
        get: operations["getAnalysisValue"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analyses/{analysis_id}/proof": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Hashes, versions and the honest anchor status
         * @description A hash detects a changed file against a trusted record. One anchor does
         *     not prevent double selling and does not certify that the calculation is
         *     true. Anchor fields are nullable and carry an explicit status of
         *     NOT_REQUESTED, PENDING, CONFIRMED or FAILED.
         */
        get: operations["getAnalysisProof"];
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
        LoginRequest: {
            username: string;
            password: string;
        };
        Timestamp: string;
        /** @description Opaque identifier. Consumers must not parse it. */
        Id: string;
        /**
         * @description What the signed-in person may do. Held on the server and never taken from a request header: a role a client can set is not an authorization.
         * @enum {string}
         */
        Role: "PROJECT_OWNER" | "VERIFIER" | "INVESTOR";
        /** @description The signed-in person. Carries no password material and no session token. */
        User: {
            user_id: components["schemas"]["Id"];
            username: string;
            display_name: string;
            role: components["schemas"]["Role"];
        };
        /** @description An opaque session token and who it belongs to. The token is random, stored only as a hash, and is not derivable from anything in a build. */
        Session: {
            token: string;
            expires_at: components["schemas"]["Timestamp"];
            user: components["schemas"]["User"];
        };
        /** @description Error envelope. It never carries a stack trace, a secret or a local filesystem path. */
        Error: {
            error: {
                code: string;
                message: string;
                details: Record<string, never>;
            };
            request_id: string;
        };
        /** @description A demonstration account this deployment turned on. It carries no password: the password stays in the environment of the service and never reaches a browser or a build. */
        DemoAccount: {
            username: string;
            display_name: string;
            role: components["schemas"]["Role"];
        };
        /** @description The demonstration accounts a person may enter with one click. An empty list is the normal answer: one-click entry exists only where somebody deliberately configured demonstration accounts. */
        DemoAccountList: {
            accounts: components["schemas"]["DemoAccount"][];
        };
        /** @description Which configured demonstration account to enter. There is no password field on purpose: the service looks the password up in its own environment, so a demonstration cannot be turned on from the client side. */
        DemoLoginRequest: {
            username: string;
        };
        /** @description SHA-256 over RFC 8785 canonical JSON or over exact file bytes. */
        Hash: string;
        /** @description GeoJSON geometry in WGS84 lon/lat order. */
        Geometry: {
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
        CatalogArea: {
            aoi_id: components["schemas"]["Id"];
            name: string;
            region: string;
            area_ha: number;
            analysis_start_year: number;
            analysis_end_year: number;
            selection_role: string;
            project_status: string;
            baseline_id: string;
            bbox: number[];
            geometry: components["schemas"]["Geometry"];
            available_years: number[];
        };
        CatalogSampleRequest: {
            request_id: components["schemas"]["Id"];
            parent_aoi_id: components["schemas"]["Id"];
            year_start: number;
            year_end: number;
            area_ha: number;
            purpose: string;
            baseline_rule: string;
            geometry: components["schemas"]["Geometry"];
        };
        PriceScenario: {
            /** @enum {string} */
            id: "low" | "base" | "high";
            rub_per_unit: number;
        };
        Source: {
            source_id: components["schemas"]["Id"];
            product: string;
            version: string;
            license_url: string;
            attribution: string;
            access_date: string;
            role: string;
        };
        Catalog: {
            schema_version: string;
            method_version: string;
            dataset_version: string;
            dataset_hash: components["schemas"]["Hash"];
            year_min: number;
            year_max: number;
            max_area_ha: number;
            raster_adapter: string;
            carbon_adapter: string;
            /**
             * @description REAL means the owning packages answered. FIXTURE means labelled vectors were replayed and every result carries a fixture label; a deployment must opt into it by name.
             * @enum {string}
             */
            engine_mode?: "REAL" | "FIXTURE";
            areas: components["schemas"]["CatalogArea"][];
            sample_requests: components["schemas"]["CatalogSampleRequest"][];
            prices: components["schemas"]["PriceScenario"][];
            sources: components["schemas"]["Source"][];
        };
        /** @description A contour to measure before it is submitted. The same geodesic algorithm as the analysis path, so a measurement never disagrees with a run. */
        AreaMeasureRequest: {
            geometry: components["schemas"]["Geometry"];
        };
        /**
         * @description BLOCKING means the finding stopped a value from being published.
         * @enum {string}
         */
        WarningSeverity: "INFO" | "WARNING" | "BLOCKING";
        /** @description A machine-stable code with a human message. Consumers switch on code and may localise message; they must not parse message. */
        Warning: {
            code: components["schemas"]["Id"];
            severity: components["schemas"]["WarningSeverity"];
            message: string;
            details: Record<string, never>;
        };
        /** @description Measured area of a normalised contour, with the limit it is judged against. An invalid contour is a measurement with valid=false and named errors, not an exception. */
        AreaMeasurement: {
            valid: boolean;
            area_ha: number | null;
            max_area_ha: number;
            within_limit: boolean;
            geometry_hash: components["schemas"]["Hash"] | null;
            geometry: components["schemas"]["Geometry"] | null;
            errors: components["schemas"]["Warning"][];
        };
        /**
         * @description Where a verification request has got to. Only a verifier moves it to FINALIZED, and only from CALCULATED: a failed run and a result that could not produce a number never advance on their own.
         * @enum {string}
         */
        RequestStatus: "DRAFT" | "SUBMITTED" | "ANALYSING" | "CALCULATED" | "FINALIZED";
        /** @description Model year of the biomass product. This is not the acquisition date of an optical scene. */
        Year: number;
        Uuid: string;
        /** @description One recorded move of a request. The history is append-only. */
        RequestEvent: {
            occurred_at: components["schemas"]["Timestamp"];
            from_status: components["schemas"]["RequestStatus"] | null;
            to_status: components["schemas"]["RequestStatus"];
            user_id: components["schemas"]["Id"] | null;
            note: string;
        };
        /** @description One contour, one period and one stated volume, followed from a draft to a finalized passport. Finalizing pins a particular passport version; it never changes a number. */
        VerificationRequest: {
            request_id: components["schemas"]["Id"];
            status: components["schemas"]["RequestStatus"];
            owner: components["schemas"]["User"];
            aoi_id: components["schemas"]["Id"] | null;
            geometry: components["schemas"]["Geometry"];
            geometry_hash: components["schemas"]["Hash"];
            area_ha: number;
            year_start: components["schemas"]["Year"];
            year_end: components["schemas"]["Year"];
            claimed_units: number | null;
            claim_pool: string;
            claim_unit: string;
            analysis_id: components["schemas"]["Uuid"] | null;
            analysis_url: string | null;
            /** @description The content hash a verifier pinned when finalizing. A later recalculation produces a new passport and never rewrites this one. */
            passport_hash: components["schemas"]["Hash"] | null;
            finalized_by: components["schemas"]["Id"] | null;
            finalized_at: components["schemas"]["Timestamp"] | null;
            created_at: components["schemas"]["Timestamp"];
            updated_at: components["schemas"]["Timestamp"];
            events: components["schemas"]["RequestEvent"][];
        };
        /** @description The requests this role may see: an owner's own, all of them for a verifier, and the finalized ones for an investor. */
        VerificationRequestList: {
            requests: components["schemas"]["VerificationRequest"][];
        };
        /** @description Either geometry or aoi_id identifies the contour, exactly as in an analysis request. */
        CreateRequest: {
            aoi_id?: components["schemas"]["Id"] | null;
            geometry?: components["schemas"]["Geometry"] | null;
            year_start: components["schemas"]["Year"];
            year_end: components["schemas"]["Year"];
            claimed_units?: number | null;
        };
        /** @description What an owner may still change while the request is a draft. The contour and the period are not among them: changing those is a different request. */
        UpdateRequest: {
            claimed_units: number | null;
        };
        /**
         * @description Every value ends in _DEMO on purpose. Nothing here exists in a registry and none of it confers a right to a carbon unit.
         * @enum {string}
         */
        DemoUnitStatus: "ISSUED_DEMO" | "TRANSFERRED_DEMO" | "RETIRED_DEMO";
        /** @description One recorded step of the demonstration. The history is append-only. */
        DemoEvent: {
            occurred_at: components["schemas"]["Timestamp"];
            from_status: components["schemas"]["DemoUnitStatus"] | null;
            to_status: components["schemas"]["DemoUnitStatus"];
            user_id: components["schemas"]["Id"] | null;
            note: string;
        };
        /** @description A demonstration of what issuing, transferring and retiring would look like. It is not a registry entry, and is_demonstration is always true. */
        DemoUnit: {
            request_id: components["schemas"]["Id"];
            status: components["schemas"]["DemoUnitStatus"];
            /** @description Copied from the passport that was finalized, so a later recalculation cannot change what was demonstrated. Issuing needs a positive q: zero and null both refuse. */
            units: number;
            passport_hash: components["schemas"]["Hash"];
            issued_by: components["schemas"]["Id"];
            issued_at: components["schemas"]["Timestamp"];
            held_by: components["schemas"]["Id"] | null;
            transferred_at: components["schemas"]["Timestamp"] | null;
            retired_by: components["schemas"]["Id"] | null;
            retired_at: components["schemas"]["Timestamp"] | null;
            /** @constant */
            is_demonstration: true;
            note: string;
            events: components["schemas"]["DemoEvent"][];
        };
        /**
         * @description A stated volume is an input label, never a calculated or verified fact.
         * @enum {string}
         */
        ClaimOrigin: "USER_INPUT" | "DEMO_INPUT";
        ClaimScope: {
            geometry_hash: components["schemas"]["Hash"];
            year_start: number;
            year_end: number;
            pool: string;
            unit: string;
        };
        /** @description Either geometry or aoi_id identifies the contour. Naming a supplied area is a shortcut for pasting its polygon and changes nothing else. */
        AnalysisRequest: {
            aoi_id?: components["schemas"]["Id"] | null;
            geometry?: components["schemas"]["Geometry"] | null;
            year_start: components["schemas"]["Year"];
            year_end: components["schemas"]["Year"];
            /** @description Optional stated volume. It never changes the calculated numbers. */
            claimed_units?: number | null;
            claim_origin?: components["schemas"]["ClaimOrigin"] | null;
            /** @description Scope the claim refers to. Omitted means the claim is stated for this request. */
            claim_scope?: components["schemas"]["ClaimScope"] | null;
            /** @default true */
            include_optical: boolean;
        };
        /**
         * @description Progress of the worker only. It says nothing about whether the science produced a number.
         * @enum {string}
         */
        JobState: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
        AnalysisAccepted: {
            analysis_id: components["schemas"]["Uuid"];
            job_state: components["schemas"]["JobState"];
            status_url: string;
            created_at: components["schemas"]["Timestamp"];
        };
        JobError: {
            code: string;
            message: string;
            details: Record<string, never>;
        };
        /** @enum {string} */
        FixtureKind: "DOC_EXAMPLE" | "UNIT_TEST_VECTOR" | "CONTRACT_FIXTURE";
        /** @description Present whenever any number came from a labelled vector rather than a computation over data/. The UI must display it. */
        FixtureLabel: {
            kind: components["schemas"]["FixtureKind"];
            label: string;
            note: string;
        };
        Identity: {
            analysis_id: components["schemas"]["Uuid"];
            input_hash: components["schemas"]["Hash"];
            geometry_hash: components["schemas"]["Hash"];
            schema_version: string;
            method_version: string;
            dataset_version: string;
            dataset_hash: components["schemas"]["Hash"];
            source_manifest_hash: components["schemas"]["Hash"];
            parameters_hash: components["schemas"]["Hash"];
            code_sha: string | null;
        };
        /**
         * @description STUB_FIXTURE means a typed placeholder adapter answered; it is never real science.
         * @enum {string}
         */
        DatasetOrigin: "COMPUTED_FROM_SUPPLIED_DATA" | "CACHED_REPLAY" | "EXTERNAL_RETRIEVAL" | "STUB_FIXTURE";
        /** @description Everything about this particular execution. Kept out of the deterministic content hash on purpose. */
        Run: {
            run_id: components["schemas"]["Uuid"];
            created_at: components["schemas"]["Timestamp"];
            dataset_origin: components["schemas"]["DatasetOrigin"];
            raster_adapter: string;
            carbon_adapter: string;
        };
        RequestSnapshot: {
            geometry: components["schemas"]["Geometry"];
            aoi_id: components["schemas"]["Id"] | null;
            year_start: components["schemas"]["Year"];
            year_end: components["schemas"]["Year"];
            claimed_units: number | null;
            claim_origin: components["schemas"]["ClaimOrigin"] | null;
            include_optical: boolean;
        };
        /** @enum {string} */
        CalculationStatus: "AVAILABLE" | "UNAVAILABLE";
        /**
         * @description Quality of the change explanation. Poor optical evidence never by itself sets q=null.
         * @enum {string}
         */
        EvidenceStatus: "SUFFICIENT" | "REVIEW_REQUIRED" | "INSUFFICIENT";
        ParentPart: {
            aoi_id: components["schemas"]["Id"];
            area_ha: number;
        };
        Areas: {
            /** @description Geodesic area of the contour that was asked about. */
            requested_ha: number;
            calculated_ha: number;
            /** @description max(0, requested - calculated): area the calculation could not cover. Never negative. */
            missing_ha: number;
            /** @description calculated - requested, signed. A small positive value is geodesic arithmetic on cell boundaries, not extra land. */
            area_difference_ha: number;
            complete: boolean;
            parent_parts: components["schemas"]["ParentPart"][];
        };
        /** @description A public share, clamped to [0, 1]. Where the arithmetic can land just outside that range, the unclamped value is published beside it. */
        Fraction: number;
        /** @description Unclamped coverage arithmetic exactly as the owning component reported it. A geodesic area sum over native cells may land a hair above 1.0; that value is preserved here and the public fraction is the clamped one. */
        CoverageFractionRaw: {
            biomass: number;
            uncertainty: number;
            baseline: number;
            optical_paired_valid: number;
        };
        /** @description Four independent coverages. Cloud in an optical scene does not reduce biomass coverage; they are never averaged together. */
        Coverage: {
            biomass_fraction: components["schemas"]["Fraction"];
            uncertainty_fraction: components["schemas"]["Fraction"];
            baseline_fraction: components["schemas"]["Fraction"];
            optical_paired_valid_fraction: components["schemas"]["Fraction"];
            coverage_fraction_raw: components["schemas"]["CoverageFractionRaw"];
        };
        TimelinePoint: {
            year: number;
            mean_agb_tdm_ha: number | null;
            mean_carbon_tc_ha: number | null;
            total_carbon_tc: number | null;
            baseline_carbon_tc_ha: number | null;
            area_ha: number;
            coverage: components["schemas"]["Fraction"];
            in_period: boolean;
            source_ref: string;
        };
        /** @description Stock difference of the accounted pool. The emission figure itself is published exactly once, in units.eproj_tco2e; this block points at it rather than restating it. Positive eproj means a loss from that pool over the period, not an instantaneous release of all its carbon. */
        Change: {
            year_start: number;
            year_end: number;
            mean_carbon_start_tc_ha: number | null;
            mean_carbon_end_tc_ha: number | null;
            total_carbon_start_tc: number | null;
            total_carbon_end_tc: number | null;
            delta_carbon_tc: number | null;
            /**
             * @description Where the single canonical Eproj lives. This block never carries a second copy of it.
             * @constant
             */
            eproj_ref: "units.eproj_tco2e";
            /** @description units.eproj_tco2e divided by the normalisation area and the period, for display only. */
            eproj_tco2e_ha_year: number | null;
            normalisation_area_ha: number | null;
            /** @constant */
            sign_convention: "POSITIVE_E_MEANS_POOL_LOSS";
            /** @constant */
            pool: "AGB_LIVE_WOODY";
        };
        /**
         * @description Mandatory input missing or unusable. The answer is null, never zero.
         * @enum {string}
         */
        UnavailableReason: "MISSING_INPUT" | "NON_FINITE_INPUT" | "NON_POSITIVE_AREA" | "NON_POSITIVE_PERIOD" | "INVALID_UNCERTAINTY_INPUT" | "INVALID_INTERVAL" | "INCOMPLETE_COVERAGE" | "BASELINE_OUT_OF_COVERAGE" | "BASELINE_UNKNOWN_AREA" | "RASTER_ANALYSIS_UNAVAILABLE";
        /** @enum {string} */
        IntervalKind: "SCENARIO" | "PROBABILISTIC";
        /**
         * @description INDEPENDENT_NATIVE_CELLS is the main scenario of the method freeze. FULL_SPATIAL_CORRELATION is published as a separate stress variant and never replaces it.
         * @enum {string}
         */
        SpatialDependence: "INDEPENDENT_NATIVE_CELLS" | "FULL_SPATIAL_CORRELATION";
        /** @description The stated assumptions of the scenario interval, typed so a consumer can display them without guessing. empirically_calibrated is always false: this interval is not calibrated against field measurements. */
        UncertaintyAssumptions: {
            spatial_dependence: components["schemas"]["SpatialDependence"];
            temporal_correlation: number;
            coverage_factor: number;
            cells: number;
            grid: string;
            pool: string;
            cf_agb: number;
            co2_per_c: number;
            /** @constant */
            empirically_calibrated: false;
            note?: string;
        };
        IntervalVariant: {
            label: string;
            spatial_dependence: components["schemas"]["SpatialDependence"];
            temporal_correlation: number;
            sd_tco2e: number;
            lower_tco2e: number;
            upper_tco2e: number;
            half_width_tco2e: number;
        };
        /** @description A scenario interval under stated assumptions. It is not an empirically calibrated confidence interval. */
        Uncertainty: {
            status: components["schemas"]["CalculationStatus"];
            unavailable_reason: components["schemas"]["UnavailableReason"] | null;
            lower_tco2e: number | null;
            upper_tco2e: number | null;
            sd_tco2e: number | null;
            method: string;
            interval_kind: components["schemas"]["IntervalKind"];
            assumptions: components["schemas"]["UncertaintyAssumptions"] | null;
            sensitivity: components["schemas"]["IntervalVariant"][];
        };
        BaselinePart: {
            aoi_id: components["schemas"]["Id"];
            area_ha: number;
            stock_start_tc_ha: number;
            stock_end_tc_ha: number;
            delta_tc_ha: number;
            delta_tc: number;
            clipped_at_zero: boolean;
        };
        /** @description Scenario baseline of the case from data/methodology/baseline.csv. It does not establish additionality or the owner's effort. */
        Baseline: {
            status: components["schemas"]["CalculationStatus"];
            unavailable_reason: components["schemas"]["UnavailableReason"] | null;
            baseline_id: string | null;
            kind: string;
            area_ha: number | null;
            delta_tc: number | null;
            delta_tc_ha: number | null;
            ebase_tco2e: number | null;
            parts: components["schemas"]["BaselinePart"][];
        };
        /**
         * @description Inputs were valid and a rule of the case gives exactly zero units.
         * @enum {string}
         */
        ZeroUnitsReason: "NON_POSITIVE_RELATIVE_RESULT" | "UNCERTAINTY_TOO_HIGH" | "ROUNDED_TO_ZERO";
        /** @description Potential units of the case. q=null and q=0 are different answers and carry different reason fields. */
        Units: {
            status: components["schemas"]["CalculationStatus"];
            unavailable_reason: components["schemas"]["UnavailableReason"] | null;
            zero_reason: components["schemas"]["ZeroUnitsReason"] | null;
            eproj_tco2e: number | null;
            ebase_tco2e: number | null;
            lk_tco2e: number | null;
            lower_tco2e: number | null;
            upper_tco2e: number | null;
            h_tco2e: number | null;
            r_tco2e: number | null;
            ratio: number | null;
            unc: number | null;
            uncertainty_deduction_tco2e: number | null;
            radj_tco2e: number | null;
            buffer_tco2e: number | null;
            rounding_residual_tco2e: number | null;
            q: number | null;
            reason_codes: string[];
        };
        ScenarioValue: {
            price_rub: number;
            value_rub: number;
        };
        /** @description Scenario prices of the case, not a market quote, a revenue forecast or a guaranteed sum. */
        ScenarioValues: {
            price_parameters_ref: string;
            /** @constant */
            unit: "RUB";
            low: components["schemas"]["ScenarioValue"] | null;
            base: components["schemas"]["ScenarioValue"] | null;
            high: components["schemas"]["ScenarioValue"] | null;
        };
        /**
         * @description NOT_APPLICABLE is the answer to a claim of zero: nothing positive was stated, so nothing was supported. A zero claim is never reported as SUPPORTED_BY_CASE.
         * @enum {string}
         */
        ClaimStatus: "NOT_PROVIDED" | "NOT_APPLICABLE" | "NOT_COMPARABLE" | "UNASSESSABLE" | "SUPPORTED_BY_CASE" | "PARTIALLY_SUPPORTED_BY_CASE" | "NOT_SUPPORTED_BY_CASE";
        /**
         * @description Why the comparison does not apply at all. NO_POSITIVE_CLAIM accompanies NOT_APPLICABLE: there was nothing positive to compare, which is not a disagreement.
         * @enum {string}
         */
        ClaimReason: "NO_POSITIVE_CLAIM";
        /**
         * @description Why a stated volume could not be compared with the calculation. A claim of zero is not here: nothing disagreed, so it carries claim.reason instead.
         * @enum {string}
         */
        ClaimMismatchReason: "INVALID_CLAIM_VALUE" | "GEOMETRY_MISMATCH" | "PERIOD_MISMATCH" | "POOL_MISMATCH" | "UNIT_MISMATCH";
        /** @description Comparison of a stated volume with q. gap_value is the scenario value of the unsupported part of the claim; it is not an established loss, a probabilistic Value at Risk or proven fraud. */
        Claim: {
            status: components["schemas"]["ClaimStatus"];
            reason: components["schemas"]["ClaimReason"] | null;
            origin: components["schemas"]["ClaimOrigin"] | null;
            comparable: boolean;
            claimed_units: number | null;
            q: number | null;
            /** @description max(0, claimed_units - q). Zero when nothing positive was claimed, null when the two are not comparable. An unsupported difference, not an established loss. */
            unsupported_gap: number | null;
            supported_share: components["schemas"]["Fraction"] | null;
            mismatch_reasons: components["schemas"]["ClaimMismatchReason"][];
            scope: components["schemas"]["ClaimScope"];
            scenario_gap_values: components["schemas"]["ScenarioValues"] | null;
            scope_note: string;
        };
        /** @enum {string} */
        ZoneFact: "TREE_COVER_LOSS" | "SPECTRAL_CHANGE_ONLY" | "RECOVERY_INDICATION";
        /**
         * @description What happened and why it happened are separate claims. Absent evidence stays UNKNOWN.
         * @enum {string}
         */
        ZoneCause: "FIRE_SUPPORTED" | "UNKNOWN" | "NOT_APPLICABLE";
        Date: string;
        DateRange: {
            start: components["schemas"]["Date"];
            end: components["schemas"]["Date"];
            uncertainty_days_min: number | null;
            uncertainty_days_max: number | null;
        };
        /** @description A change zone with its share of the stock change. Contributions are shares of one stock difference and are never added to a separately computed fire emission. */
        Zone: {
            zone_id: components["schemas"]["Id"];
            fact: components["schemas"]["ZoneFact"];
            cause: components["schemas"]["ZoneCause"];
            cause_reason: string;
            area_ha: number;
            carbon_overlap_ha: number;
            delta_carbon_tc: number;
            contribution_e_tco2e: number;
            date_range: components["schemas"]["DateRange"] | null;
            evidence_refs: string[];
            evidence: Record<string, never>;
            /** @description The artifact holding this zone's geometry, a GeoJSON FeatureCollection whose features carry zone_id. Non-null whenever zones are published, so a map can draw them without a second contract. */
            artifact_ref: components["schemas"]["Id"] | null;
        };
        /**
         * @description The three risks the supplied data can say something about. There is no aggregate risk score: adding them up would invent a number nobody measured.
         * @enum {string}
         */
        RiskCode: "FIRE" | "FOREST_LOSS" | "DATA_QUALITY";
        /** @description An observed basis for a risk, kept apart from q. A risk never adjusts the calculated units; it is shown beside them so a reader can weigh it themselves. */
        Risk: {
            code: components["schemas"]["RiskCode"];
            /** @description Whether the supplied products show the basis at all. False means nothing was found, which is not the same as an established absence. */
            observed: boolean;
            /** @description The measured quantities this rests on, copied from the owning product. No score and no probability. */
            basis: Record<string, never>;
            source_ref: components["schemas"]["Id"] | null;
            note: string;
        };
        /**
         * @description A measured year and a projected year are never the same kind of point, and a chart must not join them into one line.
         * @enum {string}
         */
        SeriesKind: "FACT" | "PROJECTION";
        ProjectionPoint: {
            year: number;
            series_kind: components["schemas"]["SeriesKind"];
            baseline_carbon_tc_ha: number | null;
        };
        /** @description The baseline trajectory of the case continued to the horizon year. It is a scenario assumption, not a forecast of what the plot will do, and it does not touch the current q. */
        Projection: {
            status: components["schemas"]["CalculationStatus"];
            unavailable_reason: components["schemas"]["UnavailableReason"] | null;
            horizon_year: number;
            points: components["schemas"]["ProjectionPoint"][];
            /** @description Always null. No projection of potential units is made, because nothing in the supplied data supports one. */
            q_projection: null;
            q_projection_note: string;
            note: string;
        };
        Scene: {
            scene_key: string;
            aoi_id: components["schemas"]["Id"] | null;
            datetime_utc: string;
            year: number;
            usable_fraction: components["schemas"]["Fraction"];
            note: string;
        };
        /** @description Quality of the change explanation, separate from whether q could be computed. */
        Evidence: {
            status: components["schemas"]["EvidenceStatus"];
            optical_paired_valid_fraction: components["schemas"]["Fraction"];
            analysed_parent: components["schemas"]["Id"] | null;
            scenes: components["schemas"]["Scene"][];
            reconciliation: Record<string, never> | null;
            warnings: components["schemas"]["Warning"][];
        };
        /**
         * @description State of this passport document. It is not the anchor status: a FINALIZED passport with no blockchain record is the normal case.
         * @enum {string}
         */
        PassportStatus: "DRAFT" | "FINALIZED";
        /**
         * @description Version link of the passport, in the vocabulary of the carbon engine that owns passports.
         * @enum {string}
         */
        ComparisonResult: "INITIAL" | "REVISION_OF_SAME_SCOPE" | "NEW_OBSERVATION" | "NOT_COMPARABLE";
        /**
         * @description How q moved between two comparable observations. A presentational summary, never a verdict on the earlier passport.
         * @enum {string}
         */
        ComparisonDirection: "UNCHANGED" | "INCREASED" | "DECREASED" | "NOT_COMPARED";
        /** @description Identity of the scientific content and its version link. passport.status and anchor.status are different axes and are never read as one: a passport is FINALIZED by a verifier, an anchor is written by a chain. */
        Passport: {
            status: components["schemas"]["PassportStatus"];
            finalized_at: components["schemas"]["Timestamp"] | null;
            content_hash: components["schemas"]["Hash"];
            report_hash: components["schemas"]["Hash"] | null;
            previous_hash: components["schemas"]["Hash"] | null;
            comparison_scope: string;
            comparison_result: components["schemas"]["ComparisonResult"];
            comparison_direction: components["schemas"]["ComparisonDirection"];
            comparison_note: string;
            created_at: components["schemas"]["Timestamp"];
        };
        /** @description Manifest-listed file. The browser receives an API url, never a filesystem path. */
        Artifact: {
            artifact_id: components["schemas"]["Id"];
            role: string;
            media_type: string;
            sha256: components["schemas"]["Hash"];
            size_bytes: number;
            url: string;
            bbox_wgs84: number[] | null;
            crs: string | null;
            resolution: number[] | null;
            resolution_units: string | null;
            unit: string | null;
            provenance: string;
        };
        /** @description A stated boundary of what the result means. Kept apart from warnings: a limitation always holds, a warning is about this run. */
        Limitation: {
            code: components["schemas"]["Id"];
            message: string;
        };
        AnalysisResult: {
            fixture: components["schemas"]["FixtureLabel"] | null;
            identity: components["schemas"]["Identity"];
            run: components["schemas"]["Run"];
            request: components["schemas"]["RequestSnapshot"];
            calculation_status: components["schemas"]["CalculationStatus"];
            evidence_status: components["schemas"]["EvidenceStatus"];
            areas: components["schemas"]["Areas"];
            coverage: components["schemas"]["Coverage"];
            timeline: components["schemas"]["TimelinePoint"][];
            change: components["schemas"]["Change"];
            uncertainty: components["schemas"]["Uncertainty"];
            baseline: components["schemas"]["Baseline"];
            units: components["schemas"]["Units"];
            scenario_values: components["schemas"]["ScenarioValues"];
            claim: components["schemas"]["Claim"];
            zones: components["schemas"]["Zone"][];
            risks: components["schemas"]["Risk"][];
            projection: components["schemas"]["Projection"];
            evidence: components["schemas"]["Evidence"];
            passport: components["schemas"]["Passport"];
            sources: components["schemas"]["Source"][];
            artifacts: components["schemas"]["Artifact"][];
            limitations: components["schemas"]["Limitation"][];
            notes: string[];
        };
        /** @description Job progress and, once SUCCEEDED, the typed result. Polling never mixes the axes. */
        Analysis: {
            analysis_id: components["schemas"]["Uuid"];
            job_state: components["schemas"]["JobState"];
            created_at: components["schemas"]["Timestamp"];
            updated_at: components["schemas"]["Timestamp"];
            attempts: number;
            status_url: string;
            report_url: string | null;
            proof_url: string | null;
            error: components["schemas"]["JobError"] | null;
            result: components["schemas"]["AnalysisResult"] | null;
        };
        Report: {
            schema_version: string;
            generated_at: components["schemas"]["Timestamp"];
            report_hash: components["schemas"]["Hash"];
            result: components["schemas"]["AnalysisResult"];
        };
        ValueScenario: {
            id: string;
            /**
             * @description USER_SCENARIO marks a price the caller supplied. It is an input, never a quotation this system stands behind.
             * @enum {string}
             */
            origin: "CASE_PARAMETER" | "USER_SCENARIO";
            price_rub: number;
            value_rub: number | null;
        };
        /** @description q multiplied by a price, and nothing else. Not a market quote, not a revenue forecast, not a guaranteed sum. */
        ValueScenarios: {
            analysis_id: components["schemas"]["Uuid"];
            q: number | null;
            /** @constant */
            unit: "RUB";
            price_parameters_ref: string;
            scenarios: components["schemas"]["ValueScenario"][];
            note: string;
        };
        /** @enum {string} */
        AnchorStatus: "NOT_REQUESTED" | "PENDING" | "CONFIRMED" | "FAILED";
        /** @description A hash anchor detects a changed file against a trusted record. It does not prevent double selling and does not certify that the calculation is true. */
        Anchor: {
            status: components["schemas"]["AnchorStatus"];
            deployment_id: string | null;
            tx_hash: string | null;
            anchored_at: components["schemas"]["Timestamp"] | null;
            note: string;
        };
        Proof: {
            analysis_id: components["schemas"]["Uuid"];
            identity: components["schemas"]["Identity"];
            passport: components["schemas"]["Passport"];
            canonical_url: string;
            report_urls: {
                json: string;
                html: string;
            };
            artifacts: components["schemas"]["Artifact"][];
            anchor: components["schemas"]["Anchor"];
            verification_note: string;
        };
    };
    responses: {
        /**
         * @description Error envelope. 401 unauthenticated; 403 the role may not do this;
         *     404 unknown analysis or artifact; 409 idempotency conflict; 422 invalid
         *     geometry, period or claim; 429 too many failed sign-in attempts;
         *     503 source unavailable or artifact integrity failure. The body never
         *     carries a stack trace, a secret, a session token or a local filesystem
         *     path.
         */
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
        /**
         * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
         *     client memory, and is never baked into a browser bundle. The caller
         *     identity and the role used for every permission check, for idempotency
         *     and for the audit log come from this session; there is no
         *     client-supplied role header, because a header a client can set is not
         *     an authorization.
         */
        Session: string;
        IdempotencyKey: string;
        /** @description Opaque identifier. Consumers must not parse it. */
        RequestId: string;
        /** @description Opaque identifier. Consumers must not parse it. */
        AnalysisId: string;
        /** @description Opaque identifier of a manifest-listed artifact. */
        ArtifactId: string;
    };
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    login: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description A session */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Session"];
                };
            };
            401: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            429: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    demoAccounts: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The demonstration accounts, possibly none */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoAccountList"];
                };
            };
            503: components["responses"]["Failure"];
        };
    };
    demoLogin: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DemoLoginRequest"];
            };
        };
        responses: {
            /** @description A session */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Session"];
                };
            };
            404: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            429: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    whoAmI: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The signed-in person */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["User"];
                };
            };
            401: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    logout: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The session is revoked */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        revoked: boolean;
                    };
                };
            };
            401: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getCatalog: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Catalog of the supplied dataset */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Catalog"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    measureArea: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AreaMeasureRequest"];
            };
        };
        responses: {
            /** @description Measurement of the normalized contour */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AreaMeasurement"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    listRequests: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Requests visible to this role */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationRequestList"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    createRequest: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateRequest"];
            };
        };
        responses: {
            /** @description The draft request */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationRequest"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getRequest: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The request */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationRequest"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    updateRequest: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateRequest"];
            };
        };
        responses: {
            /** @description The updated draft */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationRequest"];
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
    submitRequest: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The submitted request */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationRequest"];
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
    runRequestAnalysis: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The request, now analysing */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationRequest"];
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
    finalizeRequest: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The finalized request */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VerificationRequest"];
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
    getDemoUnit: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The demonstration unit */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoUnit"];
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
    issueDemoUnit: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The demonstration unit */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoUnit"];
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
    acceptDemoTransfer: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The demonstration unit */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoUnit"];
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
    retireDemoUnit: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                request_id: components["parameters"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The demonstration unit */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoUnit"];
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
    createAnalysis: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnalysisRequest"];
            };
        };
        responses: {
            /** @description Analysis queued */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisAccepted"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            409: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getAnalysis: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                analysis_id: components["parameters"]["AnalysisId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Analysis state */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Analysis"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getAnalysisArtifact: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                analysis_id: components["parameters"]["AnalysisId"];
                /** @description Opaque identifier of a manifest-listed artifact. */
                artifact_id: components["parameters"]["ArtifactId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Artifact bytes with the recorded media type */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": string;
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getAnalysisReport: {
        parameters: {
            query?: {
                format?: "json" | "html";
            };
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                analysis_id: components["parameters"]["AnalysisId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Report */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Report"];
                    "text/html": string;
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getAnalysisValue: {
        parameters: {
            query?: {
                /** @description A price of the caller's own, labelled USER_SCENARIO in the answer. */
                price_rub?: number;
            };
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                analysis_id: components["parameters"]["AnalysisId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Scenario values */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ValueScenarios"];
                };
            };
            401: components["responses"]["Failure"];
            403: components["responses"]["Failure"];
            404: components["responses"]["Failure"];
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
    getAnalysisProof: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description `Bearer <token>` from POST /auth/login. The token is opaque, is held in
                 *     client memory, and is never baked into a browser bundle. The caller
                 *     identity and the role used for every permission check, for idempotency
                 *     and for the audit log come from this session; there is no
                 *     client-supplied role header, because a header a client can set is not
                 *     an authorization.
                 */
                Authorization: components["parameters"]["Session"];
            };
            path: {
                /** @description Opaque identifier. Consumers must not parse it. */
                analysis_id: components["parameters"]["AnalysisId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Proof document */
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
            422: components["responses"]["Failure"];
            503: components["responses"]["Failure"];
        };
    };
}
