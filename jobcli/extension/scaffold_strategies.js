const fs = require('fs');
const path = require('path');

const platforms = [
    { name: 'successfactors', classPrefix: 'SuccessFactors', domains: ['sapsf.com', 'successfactors.com'] },
    { name: 'adp', classPrefix: 'Adp', domains: ['adp.com'] },
    { name: 'ashby', classPrefix: 'Ashby', domains: ['ashhq.by', 'ashbyhq.com'] },
    { name: 'smartrecruiters', classPrefix: 'SmartRecruiters', domains: ['smartrecruiters.com'] },
    { name: 'icims', classPrefix: 'Icims', domains: ['icims.com'] },
    { name: 'jobvite', classPrefix: 'Jobvite', domains: ['jobvite.com'] },
    { name: 'taleo', classPrefix: 'Taleo', domains: ['taleo.net'] },
    { name: 'workable', classPrefix: 'Workable', domains: ['workable.com'] },
    { name: 'bamboohr', classPrefix: 'BambooHr', domains: ['bamboohr.com'] },
    { name: 'paycom', classPrefix: 'Paycom', domains: ['paycom.com'] },
    { name: 'paychex', classPrefix: 'Paychex', domains: ['paychex.com'] },
    { name: 'ultipro', classPrefix: 'Ultipro', domains: ['ultipro.com'] },
    { name: 'linkedin', classPrefix: 'Linkedin', domains: ['linkedin.com'] },
    { name: 'indeed', classPrefix: 'Indeed', domains: ['indeed.com'] },
    { name: 'recruitee', classPrefix: 'Recruitee', domains: ['recruitee.com'] },
    { name: 'teamtailor', classPrefix: 'Teamtailor', domains: ['teamtailor.com'] },
    { name: 'personio', classPrefix: 'Personio', domains: ['personio.com'] },
    { name: 'oraclecloud', classPrefix: 'OracleCloud', domains: ['oraclecloud.com'] },
    { name: 'applytojob', classPrefix: 'ApplyToJob', domains: ['applytojob.com'] },
    { name: 'brassring', classPrefix: 'Brassring', domains: ['brassring.com'] },
    { name: 'rippling', classPrefix: 'Rippling', domains: ['rippling.com'] }
];

const STUB_TEMPLATE = `/**
 * {{fileName}}
 * Strategy for {{className}} application forms.
 */
class {{className}}Strategy extends GenericStrategy {
    constructor() {
        super();
        this.CONFIDENCE_THRESHOLD = 70; 
    }

    execute(normalizedData, aiEnabled) {
        console.log("Executing {{className}}Strategy...");
        
        // Basic fallback execution. Override findValueForInput if specific DOM structures are known.
        super.execute(normalizedData, aiEnabled);
    }
}

// Register with Strategy Registry
if (typeof ATSStrategyRegistry !== 'undefined') {
    ATSStrategyRegistry.register(
        (url, doc) => {{condition}},
        {{className}}Strategy
    );
}
`;

function buildCondition(domains, name) {
    if (name === 'linkedin') {
        return "url.includes('linkedin.com/jobs')";
    }
    return domains.map(d => "url.includes('" + d + "')").join(' || ');
}

// 1. Generate JS files
platforms.forEach(p => {
    const fileName = p.name + 'Strategy.js';
    const filePath = path.join(__dirname, 'atsStrategies', fileName);

    if (!fs.existsSync(filePath)) {
        const fileContent = STUB_TEMPLATE
            .replace(/{{fileName}}/g, fileName)
            .replace(/{{className}}/g, p.classPrefix)
            .replace(/{{condition}}/g, buildCondition(p.domains, p.name));

        fs.writeFileSync(filePath, fileContent);
        console.log('Created: ' + fileName);
    }
});

// 2. Update manifest.json
const manifestPath = path.join(__dirname, 'manifest.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

let matchSet = new Set(manifest.host_permissions);
let jsSet = new Set(manifest.content_scripts[0].js);

platforms.forEach(p => {
    // Add matches
    p.domains.forEach(d => matchSet.add(`*://*.${d}/*`));

    // Add js
    jsSet.add(`atsStrategies/${p.name}Strategy.js`);
});

// Convert sets back to sorted arrays (keeping original ones at top if possible, or just replacing)
// Sort matches
manifest.host_permissions = Array.from(matchSet).sort();
manifest.content_scripts[0].matches = manifest.host_permissions.filter(m => m !== "http://localhost:11434/*");

// Sort js
const coreJs = ["atsStrategies/strategyRegistry.js", "atsStrategies/genericStrategy.js"];
const uniqueStrategies = Array.from(jsSet).filter(j => !coreJs.includes(j) && j !== "content.js").sort();
manifest.content_scripts[0].js = [...coreJs, ...uniqueStrategies, "content.js"];

fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
console.log('Updated manifest.json');
