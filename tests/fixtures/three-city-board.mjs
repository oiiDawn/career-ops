// Emit three separately located openings with the same title for offline discovery checks.
const ROLE = 'Strategic Finance Manager';

console.log(JSON.stringify([
  { title: ROLE, url: 'https://boards.example.com/fixture/1001', company: 'Fixture Defense', location: 'Costa Mesa, CA' },
  { title: ROLE, url: 'https://boards.example.com/fixture/1002', company: 'Fixture Defense', location: 'Washington, DC' },
  { title: ROLE, url: 'https://boards.example.com/fixture/1003', company: 'Fixture Defense', location: 'Huntsville, AL' },
]));
