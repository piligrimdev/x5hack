export const REFERRAL_INVITEE_PERCENT = 10;
export const REFERRAL_INVITER_COUPONS = 2;
export const REFERRAL_INVITER_CASHBACK = 50;
export const REFERRAL_WINDOW_DAYS = 7;
export const REFERRAL_INACTIVE_MONTHS = 6;

export const INVITER_STEPS = [
  'Отправьте другу код — каждый новый код одноразовый, старые неиспользованные тоже работают.',
  `Друг вводит код при регистрации или входе. Уже зарегистрированным код подойдёт, только если не было покупок ${REFERRAL_INACTIVE_MONTHS} месяцев.`,
  `После активации другу сразу открывается скидка ${REFERRAL_INVITEE_PERCENT}% на ${REFERRAL_WINDOW_DAYS} дней.`,
  `Вы получите ${REFERRAL_INVITER_COUPONS} купона на колесо и ${REFERRAL_INVITER_CASHBACK} ₽ кешбека, когда друг сделает покупку в эти ${REFERRAL_WINDOW_DAYS} дней.`,
];

export const INVITEE_STEPS = [
  `Новый аккаунт с кодом: сразу скидка ${REFERRAL_INVITEE_PERCENT}% на покупки на ${REFERRAL_WINDOW_DAYS} дней.`,
  `Если аккаунт уже есть — код сработает только без покупок за ${REFERRAL_INACTIVE_MONTHS} месяцев. Иначе войдите без кода.`,
  `Друг получит купоны и кешбек, когда вы купите что-то в течение ${REFERRAL_WINDOW_DAYS} дней.`,
];
