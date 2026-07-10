import fs from 'fs';
import path from 'path';

export interface PhasePerformance {
  phase_name: string;
  percent_complete: number;
  computed_rag: string;
  source_reported_rag?: string;
  root_cause: string;
}

export interface ProjectWeeklyData {
  project_name: string;
  run_date: string;
  overall_rag: string;
  source_reported_rag: string;
  disagreement_flag: boolean;
  sub_scores: {
    schedule: string;
    milestone_health: string;
    blockers: string;
    budget_burn: string;
    stakeholder_sentiment: string;
  };
  evidence: string[];
  reasoning: string;
  data_gaps: string[];
  phase_performances?: PhasePerformance[];
}

export interface SlideData {
  slide_number: number;
  title: string;
  content: string[];
}

export function getProjectData(): ProjectWeeklyData[] {
  const weeklyDir = path.join(process.cwd(), '../data/weekly');
  if (!fs.existsSync(weeklyDir)) return [];

  const projects = fs.readdirSync(weeklyDir);
  const latestReports: ProjectWeeklyData[] = [];

  for (const project of projects) {
    const projectDir = path.join(weeklyDir, project);
    if (fs.statSync(projectDir).isDirectory()) {
      const files = fs.readdirSync(projectDir).filter(f => f.endsWith('.json'));
      if (files.length > 0) {
        // Sort files to get the latest one
        files.sort((a, b) => (a > b ? -1 : 1));
        const latestFile = path.join(projectDir, files[0]);
        const content = fs.readFileSync(latestFile, 'utf-8');
        try {
          const data = JSON.parse(content) as ProjectWeeklyData;
          latestReports.push(data);
        } catch (e) {
          console.error(`Failed to parse ${latestFile}`, e);
        }
      }
    }
  }
  return latestReports;
}

export function getDeckData(): SlideData[] {
  const deckPath = path.join(process.cwd(), 'public', 'deck.json');
  if (!fs.existsSync(deckPath)) return [];
  const content = fs.readFileSync(deckPath, 'utf-8');
  try {
    return JSON.parse(content) as SlideData[];
  } catch (e) {
    console.error('Failed to parse deck.json', e);
    return [];
  }
}
