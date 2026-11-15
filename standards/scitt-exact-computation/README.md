# Exact Computation Claim Profile for SCITT

**Individual proposal 00 · 8 November 2026 · lmtlssss🜐**

This directory publishes a proposed wire profile for portable exact-computation certificates.

- [Technical profile](SCITT_EXACT_COMPUTATION_PROFILE.md): signed statement, deterministic CBOR claim map, verification procedure, security and privacy.
- [Internet-Draft draft-lmtlssss-exact-state-contraction-00](https://datatracker.ietf.org/doc/draft-lmtlssss-exact-state-contraction/): the IETF Datatracker record. Individual submission, Informational; no IETF adoption status.
- Internet-Draft files: [text](https://www.ietf.org/archive/id/draft-lmtlssss-exact-state-contraction-00.txt) · [RFCXML v3](https://www.ietf.org/archive/id/draft-lmtlssss-exact-state-contraction-00.xml) · [HTML](https://www.ietf.org/archive/id/draft-lmtlssss-exact-state-contraction-00.html). The draft defines ᑕ. (TAA), exact state contraction, and specifies this COSE/CBOR statement profile.
- [COSE/CBOR vectors and independent verification](interop/): four registered predicates, issuer and verifier implementations in Node and Python, negative evidence cases.
- [Mathematical term and exact replay](https://github.com/lmtlssss/math/tree/main/mathematics/discrete-mathematics/exact-state-contraction): definition of ᑕ. (TAA), paper and verifier.

The proposal uses the SCITT architecture in [RFC 9943](https://www.rfc-editor.org/rfc/rfc9943.html) and COSE receipt structure in [RFC 9942](https://www.rfc-editor.org/rfc/rfc9942.html). The certificate has three distinct layers: an issuer signature, an independently checked computational claim, and an optional transparency receipt.

**Status.** Submitted to the IETF as the individual Internet-Draft [draft-lmtlssss-exact-state-contraction-00](https://datatracker.ietf.org/doc/draft-lmtlssss-exact-state-contraction/), posted 15 November 2026. An Internet-Draft has no IETF adoption or endorsement status. The submission-readiness workflow continues to recheck the independent COSE/CBOR vectors.

**Executable interoperability.** [Four registered predicates, deterministic COSE/CBOR vectors, independent Python and Node verification](interop/). Both implementations reproduce the signed statements byte-for-byte and reject altered statements. The Python verifier also rejects five correctly re-signed false mathematical claims. The test issuer and key are public fixtures; live JSON certificates remain a separate format.

This is a vendor-independent protocol proposal. Issuers can sign their own claims; relying parties check the evidence under an explicit trust policy. No existing JSON signing endpoint is represented as implementing this COSE profile.

## Submission · 15 November 2026

The [submission record](SUBMISSION_READINESS.md) gives the submitted draft name, its Datatracker record and the independent verification suite. The draft is an individual submission.
