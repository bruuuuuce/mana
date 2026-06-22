# Sample Output: change-impact-preview

## Input

```yaml
change_description: >
  I want to extract the fee calculation logic from PaymentService.processPayment()
  into a new FeeCalculator class so it can be tested independently and reused
  by the refund flow.
target_class: "PaymentService"
target_method: "processPayment"
change_type: extract
```

---

## Output: change-impact-preview report

```yaml
skill: change-impact-preview
status: ready_with_warnings
target: "PaymentService.processPayment()"
change_type: extract
warnings:
  - "Fee calculation logic accesses two private fields of PaymentService; extraction requires dependency injection or parameter passing"
```

---

### Callers Impacted

| Caller | File | Line | Must Change | Note |
|---|---|---|---|---|
| `PaymentOrchestrator` | `src/main/java/payments/PaymentOrchestrator.java` | 112 | No | Calls `processPayment()` — signature unchanged |
| `PaymentController` | `src/main/java/payments/api/PaymentController.java` | 67 | No | Calls `processPayment()` — signature unchanged |
| `PaymentServiceTest` | `src/test/java/payments/PaymentServiceTest.java` | 44 | Yes | Tests assert directly on fee calculation results; must be split or updated |
| `PaymentIntegrationTest` | `src/test/java/payments/PaymentIntegrationTest.java` | 23 | Possibly | End-to-end test exercises fee logic indirectly; review assertions |

---

### Contract Risks

| Severity | Area | Detail |
|---|---|---|
| info | Internal only | `processPayment()` is not part of a REST or event contract — extraction is internal |
| warning | DB transaction | Fee calculation accesses `FeeRuleRepository` inside the same transaction as payment creation; ensure `FeeCalculator` is injected as a Spring bean to preserve transaction propagation |

---

### Concurrency Flags

| Severity | Detail | Recommendation |
|---|---|---|
| info | No shared mutable state found in the fee calculation path | Safe to extract as a stateless Spring `@Service` |

---

### Tests To Update

- `PaymentServiceTest.shouldCalculateFeeForDomesticPayment` — directly tests fee logic on `PaymentService`; should move to `FeeCalculatorTest`
- `PaymentServiceTest.shouldApplyZeroFeeForExemptMerchant` — same; candidate for `FeeCalculatorTest`
- `PaymentIntegrationTest.shouldProcessPaymentWithCorrectFee` — end-to-end; no change needed, but verify fee assertions still pass after extraction

---

### Suggested Approach

1. Create `FeeCalculator` as a stateless `@Service` with a single public method `calculate(Payment payment)`.
2. Inject `FeeRuleRepository` into `FeeCalculator` — do not pass it as a constructor argument to keep the bean Spring-managed.
3. Annotate `FeeCalculator` with `@Transactional(propagation = MANDATORY)` to inherit the caller's transaction and avoid a new transaction boundary.
4. Inject `FeeCalculator` into `PaymentService` and replace the inline logic with the new method call.
5. Move `shouldCalculateFeeForDomesticPayment` and `shouldApplyZeroFeeForExemptMerchant` to a new `FeeCalculatorTest` class.
6. Run `PaymentIntegrationTest` after extraction to verify end-to-end fee behaviour is unchanged.

---

### Skill Status Block

```yaml
outputs:
  - callers_impacted
  - contract_risks
  - concurrency_flags
  - tests_to_update
  - suggested_approach
human_review_required: false
next_step: "Developer proceeds with FeeCalculator extraction following suggested approach. Run FeeCalculatorTest and PaymentIntegrationTest after implementation."
```
