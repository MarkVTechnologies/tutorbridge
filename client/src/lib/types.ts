export type Role = "parent" | "tutor" | "vetting_officer" | "ops_officer" | "finance_officer" | "safety_officer" | "super_admin";

export interface Me {
  id: number;
  email: string;
  phone: string;
  first_name: string;
  last_name: string;
  gender: string;
  role: Role;
  is_verified: boolean;
  is_staff_member: boolean;
  email_verified_at: string | null;
  phone_verified_at: string | null;
  totp_enabled: boolean;
  notification_prefs: Record<string, boolean>;
  consent_marketing: boolean;
  consent_location: boolean;
  permissions: string[];
  two_factor_ok: boolean;
  needs_2fa_setup: boolean;
}

export interface Level { id: number; code: string; name: string; min_rate_kobo: number; max_rate_kobo: number }
export interface Subject { id: number; slug: string; name: string }
export interface Area { id: number; name: string; slug: string; lga_id: number }
export interface RefData {
  levels: Level[];
  curricula: { id: number; code: string; name: string }[];
  subjects: Subject[];
  states: { id: number; name: string }[];
  lgas: { id: number; name: string; state_id: number }[];
  areas: Area[];
  config: {
    package_sizes: number[];
    lesson_durations_minutes: number[];
    matching_fee_kobo: number;
    late_cancel_notice_hours: number;
    late_cancel_tutor_pct: number;
    dispute_window_hours: number;
    booking_accept_hours: number;
  };
}

export interface Slot { weekday: number; start: string }

export interface TutorSubject { id: number; subject: number; subject_name: string; level: number; level_name: string; test_score: number | null; verified: boolean }

export interface TutorPublic {
  id: number;
  name: string;
  gender: string;
  photo_url: string | null;
  headline: string;
  bio: string;
  highest_qualification: string;
  years_experience: number;
  subjects: TutorSubject[];
  curricula: string[];
  areas: string[];
  home_area_name: string | null;
  hourly_rate_kobo: number;
  tier: "verified" | "gold" | "elite";
  rating_avg: string;
  rating_count: number;
  reliability_score: number;
  hours_taught: string;
  lessons_completed: number;
  badges: string[];
  accepts_special_needs: boolean;
  offers_online: boolean;
  reviews?: { rating: number; comment: string; author: string; created_at: string }[];
}

export interface Child {
  id: number;
  first_name: string;
  class_name: string;
  level: number;
  level_name: string;
  curriculum: number;
  curriculum_name: string;
  school_type: string;
  learning_notes: string;
  special_needs: boolean;
}

export interface LessonRequest {
  id: number;
  child: number;
  child_name: string;
  subjects: number[];
  subject_names: string[];
  goals: string;
  schedule: Slot[];
  lesson_minutes: number;
  start_date: string;
  area: number;
  area_name: string;
  budget_min_kobo: number;
  budget_max_kobo: number;
  preferences: Record<string, unknown>;
  is_online: boolean;
  status: string;
  status_display: string;
  sla_due_at: string | null;
  shortlist_published_at: string | null;
  created_at: string;
}

export interface Lesson {
  id: number;
  booking: number;
  tutor_name: string;
  child_name: string;
  scheduled_start: string;
  scheduled_end: string;
  status: string;
  status_display: string;
  amount_kobo: number;
  escrow_status: string;
  checkin_at: string | null;
  checkout_at: string | null;
  late_minutes: number;
  note_topics: string;
  note_homework: string;
  note_observations: string;
  confirmed_at: string | null;
  cancelled_by: string;
  cancel_reason: string;
  codes: { checkin: string | null; checkout: string } | null;
  can_dispute: boolean;
  dispute_status: string | null;
}

export interface Booking {
  id: number;
  status: string;
  status_display: string;
  tutor_id: number;
  tutor_name: string;
  parent_name: string;
  child_name: string;
  child_class: string;
  subject_names: string[];
  is_trial: boolean;
  package_size: number;
  lesson_minutes: number;
  schedule: Slot[];
  start_date: string;
  hourly_rate_kobo: number;
  lesson_price_kobo: number;
  matching_fee_kobo: number;
  matching_credit_kobo: number;
  total_kobo: number;
  area_name: string | null;
  address_visible: string | null;
  is_online: boolean;
  online_link: string;
  offer_expires_at: string | null;
  accepted_at: string | null;
  auto_renew: boolean;
  next_lesson: string | null;
  lessons_done: number;
  thread_id: number | null;
  created_at: string;
  lessons?: Lesson[];
  parent_summary?: { rating_avg: number | null; rating_count: number; cancellations: number };
}

export interface Notification { id: number; event: string; subject: string; body: string; link: string; read: boolean; created_at: string }
