spec:
  meta:
    name: muc_mvp_coding_spec
    version: "1.0.0"
    language: zh-Hant
    timezone: "Asia/Taipei"
    purpose: >
      給 AI coding / 工程代理直接生成後端 API、資料表、排程、授權驗證流程使用。
    scope:
      - auth
      - account
      - billing_profile
      - license
      - subscription
      - device_pairing
      - device_entitlement
      - manual_payment
      - alerts
      - audit_logs
      - license_hardening
    out_of_scope:
      - auto_payment_gateway
      - refund
      - reseller_commission
      - referral_discount
      - international_tax
      - auto_update_distribution
      - upload_customer_data_to_cloud
      - deep_ai_dashboard
      - complex_org_hierarchy

  business_model:
    summary: >
      帳號為主體，序號為收費單位，設備為綁定對象。
      一個帳號可擁有多個序號；一個序號只能綁一台有效設備；
      每個序號各自有自己的訂閱週期與狀態。
    rules:
      - one_account_can_have_many_licenses: true
      - one_license_only_one_active_device: true
      - one_device_only_one_active_license: true
      - multi_devices_require_multi_licenses: true
      - payment_unit_is_license: true

  roles:
    platform_admin:
      permissions:
        - manage_accounts
        - manage_licenses
        - create_payment
        - confirm_payment
        - revoke_device
        - view_alerts
        - ack_alert
        - resolve_alert
        - view_audit_logs
    user:
      permissions:
        - register
        - login
        - view_profile
        - view_licenses
        - view_subscription
        - view_devices
        - create_pair_code
        - revoke_own_device
        - update_billing_profile
    agent:
      permissions:
        - pair_device
        - poll_entitlement
        - heartbeat
        - pre_job_check

  domain_model:
    entities:
      account:
        description: "登入主體"
      billing_profile:
        description: "付款與發票資料"
      license:
        description: "商業收費單位；不可直接當授權憑證"
      subscription:
        description: "授權週期與狀態"
      device:
        description: "實際安裝執行 Agent 的設備"
      pair_code:
        description: "一次性短時效配對碼"
      device_token:
        description: "設備授權憑證，只存 hash，可 revoke"
      payment:
        description: "人工收款記錄"
      alert:
        description: "平台告警事件"
      audit_log:
        description: "append-only 稽核紀錄"

  state_machine:
    subscription_status:
      values:
        - ACTIVE
        - GRACE
        - SUSPENDED
      rules:
        ACTIVE: "可接新任務"
        GRACE: "可接新任務，但必須提醒快到期/已到期"
        SUSPENDED: "不可接新任務；已在跑任務可完成"
    device_status:
      values:
        - ACTIVE
        - REVOKED
        - REPLACED
    payment_status:
      values:
        - DRAFT
        - CONFIRMED
        - VOID
    transitions:
      - from: ACTIVE
        to: GRACE
        trigger: "period_end passed and reconciler executed"
      - from: GRACE
        to: SUSPENDED
        trigger: "grace_end passed and reconciler executed"
      - from: "*"
        to: ACTIVE
        trigger: "platform_admin confirms payment"

  subscription_policy:
    period_start_rule: "confirmed_at date in Asia/Taipei"
    period_length_rule: "+1 calendar month; same day if possible; otherwise end of month"
    period_end_time_rule: "23:59:59 Asia/Taipei on period_end_date"
    grace_period_rule: "1 day after period_end_date until 23:59:59 Asia/Taipei"
    cancel_at_period_end:
      description: "若為 true，保持 ACTIVE 到期末；到期後由排程轉 GRACE/SUSPENDED"
    examples:
      - confirmed_at: "2026-03-10T09:00:00+08:00"
        result:
          period_start_date: "2026-03-10"
          period_end_date: "2026-04-10"
          grace_end_date: "2026-04-11"

  device_security:
    local_storage:
      device_token: "store in OS secure storage"
      claude_api_key: "store in OS secure storage"
      device_id: "may store locally, preferably secure storage"
      install_id: "store in OS secure storage"
    fingerprint:
      formula: "SHA-256(install_id + platform + app_version + os_version + optional_hardware_hints)"
      strict_policy: true
      on_mismatch:
        http_status: 403
        error_code: DEVICE_MISMATCH
        action: require_repair
      notes:
        - "fingerprint is for risk control, not absolute hardware proof"
        - "do not rely on fingerprint alone as the only trust anchor"

  license_hardening:
    trust_chain:
      - license
      - pair_code
      - device_registration
      - device_token
      - entitlement_signed_response
      - short_lived_job_grant
    principles:
      - "license must never directly unlock execution"
      - "core work must not rely on one-time pre-check only"
      - "all entitlement responses must be signed by server"
      - "offline usage must be time-limited"
    minimum_security_baseline:
      - "pair_code must be one-time and short-lived"
      - "pair_code stored as hash only"
      - "device_token must be high-entropy and stored as hash only on server"
      - "device_token must be revocable"
      - "entitlement response must be signed"
      - "agent must verify signature with embedded public key"
      - "every new job must require fresh entitlement or valid job grant"
      - "offline over 15 minutes must stop accepting new jobs"

  polling_policy:
    entitlement_poll_interval_minutes: 2
    entitlement_poll_interval_max_minutes: 3
    pre_job_check_required: true
    api_failure_policy:
      less_or_equal_15_minutes: "reuse last valid signed entitlement"
      more_than_15_minutes: "conservative mode, deny new jobs"
    runtime_policy:
      ACTIVE: "allow new jobs"
      GRACE: "allow new jobs and show reminder"
      SUSPENDED: "deny new jobs"
    note: "running jobs are not force-killed"

  api:
    common:
      content_type: "application/json"
      auth_modes:
        user_api: "JWT session or secure cookie"
        device_api: "Authorization: Bearer <device_token> + X-Device-Id + X-Fingerprint"
      headers:
        device_required:
          - Authorization
          - X-Device-Id
          - X-Fingerprint
          - X-App-Version
          - X-Request-Nonce
          - X-Request-Timestamp

    endpoints:
      - name: register
        method: POST
        path: /auth/register
        auth: none
        body:
          email: string
          password: string
        response:
          account_id: string
          email: string
          status: string

      - name: login
        method: POST
        path: /auth/login
        auth: none
        body:
          email: string
          password: string
        response:
          access_token: string
          refresh_token: string
          user:
            account_id: string
            email: string

      - name: get_me
        method: GET
        path: /me
        auth: user
        response:
          account_id: string
          email: string
          status: string

      - name: get_my_licenses
        method: GET
        path: /me/licenses
        auth: user
        response:
          items:
            - license_id: string
              serial_no: string
              status: string
              subscription_status: string
              period_end_date: string

      - name: get_my_subscription
        method: GET
        path: /me/subscription
        auth: user
        response:
          items:
            - license_id: string
              subscription_status: "ACTIVE|GRACE|SUSPENDED"
              period_start_date: "YYYY-MM-DD"
              period_end_date: "YYYY-MM-DD"
              grace_end_date: "YYYY-MM-DD|null"
              cancel_at_period_end: boolean

      - name: get_my_devices
        method: GET
        path: /me/devices
        auth: user
        response:
          items:
            - device_id: string
              license_id: string
              device_name: string
              platform: string
              app_version: string
              status: "ACTIVE|REVOKED|REPLACED"
              last_seen_at: string

      - name: update_billing_profile
        method: PUT
        path: /me/billing-profile
        auth: user
        body:
          company_name: string
          tax_id: string
          invoice_title: string
          invoice_email: string
          address: string
        response:
          success: boolean

      - name: create_pair_code
        method: POST
        path: /me/pair-codes
        auth: user
        body:
          license_id: string
          device_name_hint: string
          expires_in_sec: integer
        constraints:
          expires_in_sec:
            min: 300
            max: 600
        response:
          pair_code: string
          expires_at: string

      - name: revoke_my_device
        method: POST
        path: /me/devices/{device_id}/revoke
        auth: user
        body:
          reason: string
        response:
          success: boolean

      - name: device_pair
        method: POST
        path: /api/device/pair
        auth: none
        body:
          pair_code: string
          device_name: string
          platform: string
          app_version: string
          fingerprint_hash: string
        response:
          account_id: string
          license_id: string
          device_id: string
          device_token: string
          token_expires_at: null
          initial_entitlement:
            payload:
              device_id: string
              license_id: string
              subscription_status: "ACTIVE|GRACE|SUSPENDED"
              allow_new_jobs: boolean
              grace_until: "YYYY-MM-DD|null"
              message_to_user: string
              message_to_agent: string
              job_grant_ttl_seconds: integer
            issued_at: string
            expires_at: string
            signature: string
        errors:
          - PAIR_CODE_INVALID
          - PAIR_CODE_EXPIRED
          - PAIR_CODE_USED
          - LICENSE_ALREADY_BOUND
          - DEVICE_REGISTRATION_REJECTED

      - name: device_entitlement
        method: GET
        path: /api/device/entitlement
        auth: device
        response:
          payload:
            device_id: string
            license_id: string
            subscription_status: "ACTIVE|GRACE|SUSPENDED"
            allow_new_jobs: boolean
            grace_until: "YYYY-MM-DD|null"
            message_to_user: string
            message_to_agent: string
            job_grant_ttl_seconds: integer
          issued_at: string
          expires_at: string
          signature: string
          optional_job_grant:
            grant_id: string
            device_id: string
            license_id: string
            scope: "accept_new_jobs"
            issued_at: string
            expires_at: string
            nonce: string
            signature: string
        errors:
          - DEVICE_TOKEN_INVALID
          - DEVICE_TOKEN_REVOKED
          - DEVICE_MISMATCH
          - RATE_LIMITED
          - NONCE_REPLAY
          - REQUEST_TIMESTAMP_INVALID

      - name: device_heartbeat
        method: POST
        path: /api/device/heartbeat
        auth: device
        body:
          app_version: string
          current_status: string
          last_job_at: "datetime|null"
        response:
          success: boolean
          server_time: string

      - name: device_check_before_job
        method: POST
        path: /api/device/check-before-job
        auth: device
        body:
          requested_scope: "accept_new_jobs"
        response:
          allowed: boolean
          entitlement:
            payload:
              device_id: string
              license_id: string
              subscription_status: "ACTIVE|GRACE|SUSPENDED"
              allow_new_jobs: boolean
              grace_until: "YYYY-MM-DD|null"
              message_to_user: string
              message_to_agent: string
              job_grant_ttl_seconds: integer
            issued_at: string
            expires_at: string
            signature: string
          job_grant:
            grant_id: string
            device_id: string
            license_id: string
            scope: "accept_new_jobs"
            issued_at: string
            expires_at: string
            nonce: string
            signature: string
        errors:
          - DEVICE_TOKEN_INVALID
          - DEVICE_TOKEN_REVOKED
          - DEVICE_MISMATCH
          - SUBSCRIPTION_SUSPENDED

      - name: admin_get_accounts
        method: GET
        path: /admin/accounts
        auth: platform_admin
        response:
          items:
            - account_id: string
              email: string
              status: string

      - name: admin_get_licenses
        method: GET
        path: /admin/licenses
        auth: platform_admin
        response:
          items:
            - license_id: string
              account_id: string
              serial_no: string
              status: string

      - name: admin_create_payment
        method: POST
        path: /admin/payments
        auth: platform_admin
        body:
          account_id: string
          license_id: string
          amount: integer
          currency: string
          method: "manual"
          note: string
          evidence_file_id: "string|null"
        response:
          payment_id: string
          status: "DRAFT"

      - name: admin_confirm_payment
        method: POST
        path: /admin/payments/{payment_id}/confirm
        auth: platform_admin
        body:
          confirmed_at: string
          reason: string
        response:
          success: boolean
          payment_id: string
          payment_status: "CONFIRMED"
          subscription:
            license_id: string
            status: "ACTIVE"
            period_start_date: "YYYY-MM-DD"
            period_end_date: "YYYY-MM-DD"
            grace_end_date: "YYYY-MM-DD"
        transactional_side_effects:
          - "payment.status = CONFIRMED"
          - "subscription.period_start_date = confirmed_date"
          - "subscription.period_end_date = confirmed_date + 1 month"
          - "subscription.grace_end_date = period_end_date + 1 day"
          - "subscription.cancel_at_period_end = false"
          - "subscription.status = ACTIVE"
          - "insert audit log"
          - "create alert"
          - "enqueue notification"

      - name: admin_activate_license
        method: POST
        path: /admin/licenses/{license_id}/activate
        auth: platform_admin
        response:
          success: boolean

      - name: admin_revoke_device
        method: POST
        path: /admin/devices/{device_id}/revoke
        auth: platform_admin
        body:
          reason: string
        response:
          success: boolean
        side_effects:
          - "device.status = REVOKED"
          - "revoke active device_token"
          - "insert audit log"
          - "create alert"

      - name: admin_get_alerts
        method: GET
        path: /admin/alerts
        auth: platform_admin
        response:
          items:
            - alert_id: string
              level: "INFO|WARN|CRITICAL"
              type: string
              status: "OPEN|ACK|RESOLVED"
              message: string
              created_at: string

      - name: admin_ack_alert
        method: POST
        path: /admin/alerts/{alert_id}/ack
        auth: platform_admin
        response:
          success: boolean

      - name: admin_resolve_alert
        method: POST
        path: /admin/alerts/{alert_id}/resolve
        auth: platform_admin
        response:
          success: boolean

      - name: admin_get_audit_logs
        method: GET
        path: /admin/audit-logs
        auth: platform_admin
        response:
          items:
            - audit_log_id: string
              actor_type: string
              actor_id: string
              action: string
              target_type: string
              target_id: string
              created_at: string

  response_signing:
    algorithm: "Ed25519 preferred; fallback ES256"
    signing_target: "canonical JSON of payload + issued_at + expires_at"
    public_key_distribution: "embedded in agent binary"
    rules:
      - "client must reject unsigned response"
      - "client must reject invalid signature"
      - "client must reject expired response"
      - "client must reject payload.device_id mismatch"
    canonicalization:
      required: true
      recommendation: "stable sorted JSON serialization"
    signed_response_shape:
      payload:
        device_id: string
        license_id: string
        subscription_status: string
        allow_new_jobs: boolean
        grace_until: "string|null"
        message_to_user: string
        message_to_agent: string
        job_grant_ttl_seconds: integer
      issued_at: string
      expires_at: string
      signature: string

  job_grant:
    enabled: true
    ttl_seconds:
      min: 60
      max: 300
      recommended: 180
    fields:
      - grant_id
      - device_id
      - license_id
      - scope
      - issued_at
      - expires_at
      - nonce
      - signature
    rules:
      - "required before accepting each new job"
      - "must be signature-verified"
      - "must be unexpired"
      - "must match local device_id"
      - "scope must equal accept_new_jobs"

  anti_replay:
    request_nonce_required: true
    request_timestamp_required: true
    timestamp_window_seconds: 60
    nonce_uniqueness_window_seconds: 300
    rules:
      - "same nonce cannot be reused within window"
      - "stale timestamp must be rejected"
      - "signed response TTL must be short-lived"

  anti_fake_server:
    certificate_pinning:
      enabled: true
      mode: "public key pinning preferred"
    base_url_policy:
      user_editable: false
      multi_env: "build-time or signed config only"
    rules:
      - "agent must not trust arbitrary TLS endpoint"
      - "agent must not expose editable license server URL in normal UI"
      - "pinning alone is insufficient; response signing is mandatory"

  anomaly_detection:
    triggers:
      - same_token_multiple_device_ids_short_window
      - same_token_multiple_ips_short_window
      - frequent_fingerprint_changes
      - same_license_multiple_device_switches_short_window
      - repeated_nonce_replay
      - signature_verification_failures
    actions:
      info:
        - log_only
      warn:
        - create_alert
        - require_repair_if_needed
      critical:
        - revoke_token
        - suspend_new_jobs
        - create_alert

  database:
    conventions:
      id_type: "uuid or ulid"
      timestamps: "created_at, updated_at"
      soft_delete: "avoid for security-critical tables; prefer status fields"
    tables:
      accounts:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: email, type: varchar, unique: true }
          - { name: password_hash, type: varchar }
          - { name: status, type: varchar }
          - { name: created_at, type: timestamptz }
          - { name: updated_at, type: timestamptz }

      billing_profiles:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: account_id, type: uuid, fk: accounts.id, unique: true }
          - { name: company_name, type: varchar }
          - { name: tax_id, type: varchar }
          - { name: invoice_title, type: varchar }
          - { name: invoice_email, type: varchar }
          - { name: address, type: varchar }
          - { name: created_at, type: timestamptz }
          - { name: updated_at, type: timestamptz }

      licenses:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: account_id, type: uuid, fk: accounts.id, index: true }
          - { name: serial_no, type: varchar, unique: true }
          - { name: status, type: varchar }
          - { name: created_at, type: timestamptz }
          - { name: updated_at, type: timestamptz }

      subscriptions:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: license_id, type: uuid, fk: licenses.id, unique: true }
          - { name: status, type: varchar, index: true }
          - { name: period_start_date, type: date }
          - { name: period_end_date, type: date, index: true }
          - { name: grace_end_date, type: date, index: true }
          - { name: cancel_at_period_end, type: boolean, default: false }
          - { name: last_state_calc_at, type: timestamptz }
          - { name: created_at, type: timestamptz }
          - { name: updated_at, type: timestamptz }

      devices:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: account_id, type: uuid, fk: accounts.id, index: true }
          - { name: license_id, type: uuid, fk: licenses.id, index: true }
          - { name: device_name, type: varchar }
          - { name: platform, type: varchar }
          - { name: app_version, type: varchar }
          - { name: fingerprint_hash, type: varchar, index: true }
          - { name: status, type: varchar, index: true }
          - { name: last_seen_at, type: timestamptz, index: true }
          - { name: created_at, type: timestamptz }
          - { name: updated_at, type: timestamptz }
        constraints:
          - "only one ACTIVE device per license_id"

      device_tokens:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: device_id, type: uuid, fk: devices.id, index: true }
          - { name: token_hash, type: varchar, index: true }
          - { name: revoked_at, type: timestamptz, nullable: true }
          - { name: created_at, type: timestamptz }
        notes:
          - "store only token hash, never plain token"

      pair_codes:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: account_id, type: uuid, fk: accounts.id, index: true }
          - { name: license_id, type: uuid, fk: licenses.id, index: true }
          - { name: code_hash, type: varchar, index: true }
          - { name: expires_at, type: timestamptz, index: true }
          - { name: used_at, type: timestamptz, nullable: true }
          - { name: created_by_user_id, type: uuid, fk: accounts.id }
          - { name: created_at, type: timestamptz }

      payments:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: account_id, type: uuid, fk: accounts.id, index: true }
          - { name: license_id, type: uuid, fk: licenses.id, index: true }
          - { name: amount, type: integer }
          - { name: currency, type: varchar }
          - { name: method, type: varchar }
          - { name: status, type: varchar, index: true }
          - { name: confirmed_at, type: timestamptz, nullable: true }
          - { name: note, type: text }
          - { name: evidence_file_id, type: uuid, nullable: true }
          - { name: created_by_platform_user_id, type: uuid }
          - { name: created_at, type: timestamptz }
          - { name: updated_at, type: timestamptz }

      alerts:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: level, type: varchar, index: true }
          - { name: type, type: varchar, index: true }
          - { name: account_id, type: uuid, fk: accounts.id, nullable: true, index: true }
          - { name: license_id, type: uuid, fk: licenses.id, nullable: true, index: true }
          - { name: status, type: varchar, index: true }
          - { name: message, type: text }
          - { name: meta_json, type: jsonb }
          - { name: created_at, type: timestamptz }
          - { name: updated_at, type: timestamptz }

      audit_logs:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: actor_type, type: varchar, index: true }
          - { name: actor_id, type: uuid, nullable: true, index: true }
          - { name: action, type: varchar, index: true }
          - { name: target_type, type: varchar, index: true }
          - { name: target_id, type: uuid, nullable: true, index: true }
          - { name: ip, type: varchar, nullable: true }
          - { name: user_agent, type: text, nullable: true }
          - { name: request_id, type: varchar, nullable: true, index: true }
          - { name: before_json, type: jsonb, nullable: true }
          - { name: after_json, type: jsonb, nullable: true }
          - { name: created_at, type: timestamptz, index: true }
        rules:
          - "append-only"
          - "no delete API"
          - "DB permission should deny delete/update if possible"

      files:
        columns:
          - { name: id, type: uuid, pk: true }
          - { name: storage_key, type: varchar }
          - { name: content_type, type: varchar }
          - { name: size, type: bigint }
          - { name: sha256, type: varchar, index: true }
          - { name: created_at, type: timestamptz }

  background_jobs:
    subscription_state_reconciler:
      schedule: "every 5 minutes"
      logic:
        - "if now > grace_end_datetime => SUSPENDED"
        - "else if now > period_end_datetime => GRACE"
        - "else ACTIVE"
      on_state_changed:
        - "insert audit log"
        - "create alert"
        - "enqueue notification"

    notification_sender:
      trigger: "queue-based"
      responsibility:
        - send_email
        - retry_on_failure
        - store_delivery_result

    invoice_issue_worker:
      schedule: "queue-based"
      current_mvp_policy: "skeleton only; actual invoice integration can be deferred"
      future_trigger: "after payment confirmation"

  rate_limit:
    device_entitlement:
      by_device_id_per_minute: 60
      by_account_per_minute: 600
      by_ip_per_minute: 300
    pair_api:
      by_ip_per_10_minutes: 20
    rules:
      - "return HTTP 429 with RATE_LIMITED"

  audit_and_alerting:
    required_audit_events:
      - PAIR_CODE_CREATED
      - PAIR_CODE_USED
      - PAIR_CODE_REJECTED
      - DEVICE_REGISTERED
      - DEVICE_REVOKED
      - DEVICE_TOKEN_ISSUED
      - DEVICE_TOKEN_REVOKED
      - ENTITLEMENT_CHECK_FAILED
      - FINGERPRINT_MISMATCH
      - NONCE_REPLAY
      - PAYMENT_CONFIRMED
      - SUBSCRIPTION_STATE_CHANGED
    alert_levels:
      INFO:
        - PAYMENT_CONFIRMED
        - DEVICE_REGISTERED
      WARN:
        - SUBSCRIPTION_GRACE
        - FREQUENT_FAILED_PAIRING
        - FINGERPRINT_CHANGED
      CRITICAL:
        - SUBSCRIPTION_SUSPENDED
        - TOKEN_REPLAY_SUSPECTED
        - SIGNATURE_VERIFICATION_FAILED
        - SAME_TOKEN_MULTI_DEVICE

  error_codes:
    auth:
      - INVALID_CREDENTIALS
      - UNAUTHORIZED
      - FORBIDDEN
    pairing:
      - PAIR_CODE_INVALID
      - PAIR_CODE_EXPIRED
      - PAIR_CODE_USED
      - LICENSE_ALREADY_BOUND
      - DEVICE_REGISTRATION_REJECTED
    device_auth:
      - DEVICE_TOKEN_INVALID
      - DEVICE_TOKEN_REVOKED
      - DEVICE_MISMATCH
      - REQUEST_TIMESTAMP_INVALID
      - NONCE_REPLAY
      - RATE_LIMITED
    subscription:
      - SUBSCRIPTION_SUSPENDED
      - SUBSCRIPTION_NOT_FOUND
    generic:
      - VALIDATION_ERROR
      - INTERNAL_ERROR

  implementation_requirements_for_ai:
    backend_style:
      - "use modular monolith architecture"
      - "separate modules by domain, not by controller only"
      - "all state-changing endpoints must be transactional where needed"
      - "all datetime stored in UTC, business logic evaluated in Asia/Taipei"
    security_rules:
      - "never store plain pair_code"
      - "never store plain device_token"
      - "never trust unsigned entitlement"
      - "always verify device_id and fingerprint"
      - "always append audit logs for critical actions"
    coding_rules:
      - "generate typed DTOs / schemas"
      - "use enum for all statuses"
      - "return stable error codes"
      - "add idempotency protection for payment confirmation if possible"
      - "make signature verification library replaceable"
      - "make rate limit configurable"
    testing_requirements:
      - "unit tests for subscription state transitions"
      - "unit tests for pair code validation"
      - "unit tests for entitlement signature verification"
      - "unit tests for offline policy"
      - "integration tests for payment confirmation -> subscription activation"
      - "integration tests for revoked device -> entitlement denied"
      - "integration tests for fingerprint mismatch -> 403 DEVICE_MISMATCH"

  acceptance_criteria:
    - "user can register and login"
    - "user can view license/subscription/device list"
    - "user can create one-time pair code"
    - "agent can pair and receive device_token exactly once"
    - "agent can poll entitlement every 2-3 minutes"
    - "agent denies new jobs when SUSPENDED"
    - "platform admin can confirm payment and reactivate subscription"
    - "reconciler can move ACTIVE -> GRACE -> SUSPENDED correctly"
    - "entitlement response is signed and client-verifiable"
    - "revoked device token can no longer access entitlement"