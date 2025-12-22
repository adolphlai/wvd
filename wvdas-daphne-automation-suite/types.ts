
export enum TabType {
  General = '基础设置',
  Battle = '战斗策略',
  Skills = '技能矩阵',
  Advanced = '高级优化',
  Stats = '统计数据'
}

export interface AppSettings {
  port: string;
  dungeon: string;
  chestOpener: string;
  skipPostBattleRestore: boolean;
  skipPostChestRestore: boolean;
  resumeOptimization: boolean;
  strongSkillAfterRestart: boolean;
  strongSkillAfterReturn: boolean;
  hotelRest: boolean;
  restInterval: number;
  luxuryRoom: boolean;
  karma: string;
  adjustKarma: boolean;
  jumpToTriumph: boolean;
  autoBattle: boolean;
  oneAoePerBattle: boolean;
  autoBattleAfterAoe: boolean;
  enableAllSkills: boolean;
  enableRowAoe: boolean;
  enableAllAoe: boolean;
  enableSecretAoe: boolean;
  enableSingleTarget: boolean;
  enableCrowdControl: boolean;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
}
