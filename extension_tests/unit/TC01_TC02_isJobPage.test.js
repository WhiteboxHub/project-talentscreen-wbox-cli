/**
 * TC-01 & TC-02: isJobPage() function
 *
 * Extracted from content.js for pure unit testing.
 * Tests URL-based and DOM-based job page detection.
 */

// ─── Inline the function under test ───────────────────────────────────────────
function isJobPage() {
    // In test environment, use global.mockUrl if available, otherwise window.location.href
    const url = (global.mockUrl || window.location.href).toLowerCase();
    const jobKeywords = [
        'job', 'apply', 'career', 'hiring',
        'lever.co', 'greenhouse.io', 'workday', 'ashbyhq', 'bamboohr', 'smartrecruiters',
        'icims', 'taleo', 'brassring', 'successfactors', 'oraclecloud', 'indeed.com',
        'linkedin.com/jobs', 'recruitee', 'personio', 'teamtailor', 'workable'
    ];

    const matchedUrl = jobKeywords.find(k => url.includes(k));
    if (matchedUrl) return true;

    const jobFieldIndicators = [
        'resume', 'cv', 'cover_letter', 'linkedin_profile', 'phone_number',
        'years_of_experience', 'work_authorization', 'sponsorship'
    ];
    const inputs = Array.from(document.querySelectorAll('input, label'))
        .map(e => (e.name || e.id || e.innerText || '').toLowerCase());
    const matchedField = jobFieldIndicators.find(k => inputs.some(i => i.includes(k)));
    if (matchedField) return true;

    return false;
}

// ─── Helper: set window.location.href safely in jsdom ────────────────────────
// jsdom does not support `delete window.location` + reassignment, and cross-origin
// pushState throws SecurityError. We bypass this by injecting global.mockUrl.
function setUrl(url) {
    global.mockUrl = url;
}

// ─── Helper: inject DOM inputs ────────────────────────────────────────────────
function injectInput(id) {
    const el = document.createElement('input');
    el.id = id;
    document.body.appendChild(el);
}

beforeEach(() => {
    document.body.innerHTML = ''; // clear DOM
});

// ─────────────────────────────────────────────────────────────────────────────
// TC-01: URL-based ATS detection
// ─────────────────────────────────────────────────────────────────────────────
describe('TC-01 | isJobPage() — ATS URL detection', () => {

    test('TC-01-01 ✅ Greenhouse.io URL → true', () => {
        setUrl('https://boards.greenhouse.io/acme/jobs/12345');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-02 ✅ Lever.co URL → true', () => {
        setUrl('https://jobs.lever.co/example-company/abc-123');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-03 ✅ Workday URL → true', () => {
        setUrl('https://acme.myworkdayjobs.com/en-US/External/job/Software-Engineer');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-04 ✅ Ashby HQ URL → true', () => {
        setUrl('https://jobs.ashbyhq.com/company/role-id');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-05 ✅ SmartRecruiters URL → true', () => {
        setUrl('https://jobs.smartrecruiters.com/CompanyName/role');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-06 ✅ Indeed URL → true', () => {
        setUrl('https://www.indeed.com/viewjob?jk=abc123');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-07 ✅ LinkedIn Jobs URL → true', () => {
        setUrl('https://www.linkedin.com/jobs/view/12345678');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-08 ✅ BambooHR URL → true', () => {
        setUrl('https://company.bamboohr.com/jobs/view.php?id=1');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-09 ✅ Generic /apply URL → true', () => {
        setUrl('https://company.com/apply/software-engineer');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-10 ✅ Generic /careers URL → true', () => {
        setUrl('https://company.com/careers/open-roles');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-11 ✅ Workable URL → true', () => {
        setUrl('https://apply.workable.com/company/j/role-id/');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-12 ✅ Taleo URL → true', () => {
        setUrl('https://company.taleo.net/careersection/jobs');
        expect(isJobPage()).toBe(true);
    });

    test('TC-01-13 ❌ Google homepage → false', () => {
        document.body.innerHTML = ''; // ensure no job form fields
        setUrl('https://www.google.com');
        expect(isJobPage()).toBe(false);
    });

    test('TC-01-14 ❌ YouTube URL → false', () => {
        setUrl('https://www.youtube.com/watch?v=abc');
        expect(isJobPage()).toBe(false);
    });

    test('TC-01-15 ❌ Amazon shopping URL → false', () => {
        setUrl('https://www.amazon.com/dp/B08N5KWB9H');
        expect(isJobPage()).toBe(false);
    });

    test('TC-01-16 ❌ Github repo URL → false', () => {
        setUrl('https://github.com/facebook/react');
        expect(isJobPage()).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// TC-02: DOM-based field detection (non-ATS URL but job form fields present)
// ─────────────────────────────────────────────────────────────────────────────
describe('TC-02 | isJobPage() — DOM field detection', () => {

    test('TC-02-01 ✅ Input id="resume" on non-ATS page → true', () => {
        setUrl('https://company.com/apply-here');
        injectInput('resume');
        expect(isJobPage()).toBe(true);
    });

    test('TC-02-02 ✅ Input name="phone_number" → true', () => {
        setUrl('https://company.com/form');
        const el = document.createElement('input');
        el.name = 'phone_number';
        document.body.appendChild(el);
        expect(isJobPage()).toBe(true);
    });

    test('TC-02-03 ✅ Input id="work_authorization" → true', () => {
        setUrl('https://company.com/form');
        injectInput('work_authorization');
        expect(isJobPage()).toBe(true);
    });

    test('TC-02-04 ✅ Input id="sponsorship" → true', () => {
        setUrl('https://company.com/form');
        injectInput('sponsorship');
        expect(isJobPage()).toBe(true);
    });

    test('TC-02-05 ❌ Non-ATS URL with only username/password inputs → false', () => {
        setUrl('https://myapp.com/login');
        injectInput('username');
        injectInput('password');
        expect(isJobPage()).toBe(false);
    });

    test('TC-02-06 ❌ Empty DOM, generic URL → false', () => {
        setUrl('https://myapp.com/dashboard');
        expect(isJobPage()).toBe(false);
    });
});
