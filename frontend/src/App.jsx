import { useEffect, useMemo, useState } from 'react'
import heroImage from './assets/hero.png'

const API = '/api'
const MEMBERSHIP_KEY = 'ortu_membership_token'

const formatDate = (value) => new Intl.DateTimeFormat('en-GB', {
  weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
}).format(new Date(value))

const request = async (path, options = {}) => {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const data = response.status === 204 ? null : await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || 'Something went wrong. Please try again.')
  return data
}

function Mark() {
  return <a className="brand" href="#top" aria-label="ORTU Fitness home"><span className="brandMark">O</span><span>ORTU <b>FITNESS</b></span></a>
}

function Modal({ title, onClose, wide, children }) {
  useEffect(() => {
    const close = (event) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [onClose])
  return <div className="modalBackdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <section className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <button className="modalClose" onClick={onClose} aria-label="Close">×</button>
      <p className="eyebrow">ORTU FITNESS</p><h2 id="modal-title">{title}</h2>{children}
    </section>
  </div>
}

function App() {
  const [site, setSite] = useState({ plans: [], sessions: [], payments_ready: false })
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [joinPlan, setJoinPlan] = useState(null)
  const [bookingSession, setBookingSession] = useState(null)
  const [showMember, setShowMember] = useState(false)
  const [showAdmin, setShowAdmin] = useState(false)
  const [showSignup, setShowSignup] = useState(false)
  const [membershipToken, setMembershipToken] = useState(() => localStorage.getItem(MEMBERSHIP_KEY) || '')
  const [memberProfile, setMemberProfile] = useState(() => { try { return JSON.parse(localStorage.getItem('ortu_member_profile') || 'null') } catch { return null } })
  const saveProfile = (member) => { if (member) { setMemberProfile(member); localStorage.setItem('ortu_member_profile', JSON.stringify(member)) } }
  const chooseJoin = (plan) => {
    if (!memberProfile && !membershipToken) {
      setNotice('ORTU approves new members before plans can be purchased — please send a member record request first.')
      setShowSignup(true)
      return
    }
    setJoinPlan(plan)
  }

  const loadSite = () => request('/site').then(setSite).catch((e) => setNotice(e.message)).finally(() => setLoading(false))
  useEffect(loadSite, [])
  useEffect(() => {
    const query = new URLSearchParams(window.location.search)
    const returnedToken = query.get('membership_token')
    if (returnedToken) {
      localStorage.setItem(MEMBERSHIP_KEY, returnedToken)
      setMembershipToken(returnedToken)
    }
    if (query.get('payment') === 'success') { setNotice('Welcome to ORTU Fitness — your membership is active and ready to book.'); setShowMember(true) }
    if (query.get('payment') === 'failed') setNotice('We could not confirm the Direct Debit. No booking was made — please try again or contact the studio.')
    if (query.get('payment') === 'cancelled') setNotice('Payment setup was cancelled. You can choose a plan whenever you are ready.')
    if (query.has('payment')) window.history.replaceState({}, '', window.location.pathname)
  }, [])

  const nextSessions = useMemo(() => site.sessions.slice(0, 8), [site.sessions])
  const chooseBooking = (session) => {
    if (!membershipToken) { setNotice('Choose a membership first, then return to book your class.'); document.getElementById('memberships')?.scrollIntoView({ behavior: 'smooth' }); return }
    setBookingSession(session)
  }

  return <div id="top">
    <header className="header">
      <Mark />
      <nav aria-label="Main navigation"><a href="#classes">Classes</a><a href="#memberships">Memberships</a><a href="#about">Why ORTU</a></nav>
      <div className="headerActions"><button className="textButton" onClick={() => setShowSignup(true)}>Become a member</button><button className="textButton" onClick={() => setShowMember(true)}>My bookings</button><a className="button small" href="#classes">Book a class</a></div>
    </header>

    {notice && <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}

    <main>
      <section className="hero">
        <img src={heroImage} alt="A welcoming ORTU Fitness small-group workout with a coach" />
        <div className="heroShade" />
        <div className="heroContent">
          <p className="eyebrow light">SMALL-GROUP FITNESS · BIG ENERGY</p>
          <h1>Move better.<br /><em>Feel stronger.</em></h1>
          <p>Flexible classes, expert coaching and a community that makes showing up the best part of your day.</p>
          <div className="heroActions"><a className="button" href="#classes">Find your class <span>↗</span></a><a className="button ghost" href="#memberships">View memberships</a></div>
          <div className="heroProof"><span><b>6</b> flexible plans</span><span><b>Live</b> class availability</span><span><b>Secure</b> Direct Debit</span></div>
        </div>
      </section>

      <section className="marquee" aria-label="ORTU values"><span>STRENGTH</span><i>✦</i><span>MOVEMENT</span><i>✦</i><span>COMMUNITY</span><i>✦</i><span>CONFIDENCE</span></section>

      <section className="section schedule" id="classes">
        <div className="sectionIntro"><div><p className="eyebrow">LIVE TIMETABLE</p><h2>Your next class<br />starts here.</h2></div><p>See genuine spaces before you book. When a class reaches capacity, bookings close automatically—no overcrowding, ever.</p></div>
        {loading ? <div className="emptyState">Loading the latest classes…</div> : nextSessions.length ? <div className="classGrid">
          {nextSessions.map((session) => <article className={`classCard ${session.is_full ? 'full' : ''}`} key={session.id}>
            <div className="classDate"><b>{new Date(session.start_at).toLocaleDateString('en-GB', { day: '2-digit' })}</b><span>{new Date(session.start_at).toLocaleDateString('en-GB', { month: 'short' }).toUpperCase()}</span></div>
            <div className="classMain"><span className="pill">{session.coach_name}</span><h3>{session.name}</h3><p>{formatDate(session.start_at)} · {session.location}</p></div>
            <div className="availability"><span className={session.is_full ? 'danger' : session.remaining <= 3 ? 'warning' : ''}>{session.is_full ? 'Class full' : `${session.remaining} ${session.remaining === 1 ? 'space' : 'spaces'} left`}</span><div className="meter"><i style={{ width: `${Math.min(100, (session.booked / session.capacity) * 100)}%` }} /></div></div>
            <button className="arrowButton" disabled={session.is_full} onClick={() => chooseBooking(session)} aria-label={`Book ${session.name}`}>{session.is_full ? '×' : '→'}</button>
          </article>)}
        </div> : <div className="emptyState"><b>New timetable coming shortly.</b><span>The studio is setting up its first live class schedule. Check back soon.</span></div>}
        <p className="policyNote">Please note: online cancellation closes 1 hour before a class starts.</p>
      </section>

      <section className="section memberships" id="memberships">
        <div className="sectionIntro inverted"><div><p className="eyebrow light">MEMBERSHIPS</p><h2>Fitness that fits<br />your rhythm.</h2></div><p>Start with one class, choose a flexible pass or build a steady monthly routine. Payments are collected securely by GoCardless.</p></div>
        <div className="planGrid">{site.plans.map((plan) => <article className={`planCard ${plan.featured ? 'featured' : ''}`} key={plan.slug}>
          {plan.featured && <span className="popular">MOST POPULAR</span>}<p className="planType">{plan.billing_kind === 'recurring' ? 'MONTHLY MEMBERSHIP' : 'FLEXIBLE PASS'}</p><h3>{plan.name}</h3><p className="planDesc">{plan.description}</p><div className="price"><b>{plan.price}</b><span>{plan.billing_kind === 'recurring' ? '/ month' : 'one-off'}</span></div>
          <ul><li>Book from the live timetable</li><li>Manage bookings online</li><li>Secure GoCardless payment</li></ul>
          <button className={plan.featured ? 'button' : 'button outline'} onClick={() => chooseJoin(plan)}>Choose plan</button>
        </article>)}</div>
        <div className="joinFirst">New to ORTU? <button onClick={() => setShowSignup(true)}>Send a member record request</button> — the club approves every new member before a plan can be purchased.</div>
        {!site.payments_ready && <div className="setupBanner"><b>Payments are in setup mode.</b> Add the GoCardless environment settings before accepting live memberships.</div>}
      </section>

      <section className="section values" id="about">
        <div className="valuesLead"><p className="eyebrow">WHY ORTU</p><h2>Good training<br />changes more<br />than your body.</h2><p>ORTU is designed for real people: expert direction, encouraging energy and enough variety to keep you moving forward.</p></div>
        <div className="valueCards"><article><span>01</span><h3>Coaching that sees you</h3><p>Every movement can be scaled. Come as you are and leave feeling capable.</p></article><article><span>02</span><h3>Small groups, real attention</h3><p>Class capacities protect the quality, safety and energy of every session.</p></article><article><span>03</span><h3>Consistency without pressure</h3><p>Choose one session or unlimited access. Your routine can grow with you.</p></article></div>
      </section>

      <section className="cta"><p className="eyebrow light">READY WHEN YOU ARE</p><h2>Your strongest chapter<br />can start today.</h2><a className="button" href="#memberships">Choose your membership <span>↗</span></a></section>
    </main>

    <footer><div><Mark /><p>Small-group health and fitness with room for everyone to progress.</p></div><div><b>EXPLORE</b><a href="#classes">Classes</a><a href="#memberships">Memberships</a><a href="#about">Why ORTU</a></div><div><b>MEMBERS</b><button onClick={() => setShowSignup(true)}>Become a member</button><button onClick={() => setShowMember(true)}>My bookings</button><button onClick={() => setShowAdmin(true)}>Studio login</button></div><div><b>PAYMENTS</b><p>Securely processed by GoCardless</p><p>Cancellation cutoff: 1 hour</p></div></footer>

    {showSignup && <SignupModal onClose={() => setShowSignup(false)} />}
    {joinPlan && <JoinModal plan={joinPlan} paymentsReady={site.payments_ready} phoneForLogin={!!site.member_login_channels?.phone} profile={memberProfile} onClose={() => setJoinPlan(null)} setNotice={setNotice} />}
    {bookingSession && <BookingModal session={bookingSession} membershipToken={membershipToken} onClose={() => setBookingSession(null)} onBooked={() => { setBookingSession(null); loadSite(); setNotice('Class booked — we look forward to seeing you.'); setShowMember(true) }} />}
    {showMember && <MemberModal initialToken={membershipToken} channels={site.member_login_channels || {}} onToken={(token) => { setMembershipToken(token); localStorage.setItem(MEMBERSHIP_KEY, token) }} onProfile={saveProfile} onNeedsPlan={() => { setShowMember(false); setNotice("You're approved — choose your membership plan below to start booking classes."); document.getElementById('memberships')?.scrollIntoView({ behavior: 'smooth' }) }} onClose={() => setShowMember(false)} onChanged={loadSite} />}
    {showAdmin && <AdminModal onClose={() => setShowAdmin(false)} onChanged={loadSite} />}
  </div>
}

function JoinModal({ plan, paymentsReady, phoneForLogin, profile, onClose, setNotice }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    try {
      const data = await request('/memberships/checkout', { method: 'POST', body: JSON.stringify({ plan_slug: plan.slug, first_name: form.get('first_name'), last_name: form.get('last_name'), email: form.get('email'), phone: form.get('phone'), marketing_opt_in: form.get('marketing_opt_in') === 'on' }) })
      localStorage.setItem(MEMBERSHIP_KEY, data.membership_token)
      window.location.assign(data.checkout_url)
    } catch (e) { setError(e.message); setBusy(false) }
  }
  return <Modal title={`Join with ${plan.name}`} onClose={onClose}><div className="checkoutSummary"><span>{plan.description}</span><b>{plan.price}{plan.billing_kind === 'recurring' ? ' monthly' : ''}</b></div><form className="form" onSubmit={submit}><div className="twoCols"><label>First name<input required name="first_name" defaultValue={profile?.first_name} autoComplete="given-name" /></label><label>Last name<input required name="last_name" defaultValue={profile?.last_name} autoComplete="family-name" /></label></div><label>Email address <small>the one on your member record</small><input required type="email" name="email" defaultValue={profile?.email} autoComplete="email" /></label><label>Mobile number <small>{phoneForLogin ? 'with country code — you log in to your bookings with it' : 'optional'}</small><input name="phone" type="tel" autoComplete="tel" required={phoneForLogin} defaultValue={profile?.phone || ''} placeholder="+44 7700 900123" /></label><label className="check"><input type="checkbox" name="marketing_opt_in" /><span>Send me useful ORTU updates and offers.</span></label>{error && <p className="formError">{error}</p>}<button className="button wide" disabled={busy || !paymentsReady}>{busy ? 'Opening secure payment…' : paymentsReady ? 'Continue to GoCardless' : 'Payments not yet connected'}</button><p className="fineprint">Your bank details are entered on GoCardless’s secure hosted payment page. ORTU does not store them.</p></form></Modal>
}

function BookingModal({ session, membershipToken, onClose, onBooked }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const confirm = async () => { setBusy(true); setError(''); try { await request('/bookings', { method: 'POST', body: JSON.stringify({ membership_token: membershipToken, session_id: session.id }) }); onBooked() } catch (e) { setError(e.message); setBusy(false) } }
  return <Modal title="Confirm your class" onClose={onClose}><div className="bookingConfirm"><span className="pill">{session.coach_name}</span><h3>{session.name}</h3><p>{formatDate(session.start_at)}</p><p>{session.location}</p><div className="bookingRule"><b>{session.remaining} spaces currently available</b><span>Bookings are confirmed live and cannot exceed the class capacity.</span></div>{error && <p className="formError">{error}</p>}<button className="button wide" disabled={busy} onClick={confirm}>{busy ? 'Securing your space…' : 'Confirm booking'}</button></div></Modal>
}

function MemberModal({ initialToken, channels = {}, onToken, onProfile, onNeedsPlan, onClose, onChanged }) {
  const [token, setToken] = useState(initialToken); const [dashboard, setDashboard] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState(channels.password ? 'password' : channels.email ? 'email' : channels.phone ? 'phone' : 'code')
  const [email, setEmail] = useState(''); const [phone, setPhone] = useState(''); const [channel, setChannel] = useState('whatsapp'); const [password, setPassword] = useState('')
  const [sent, setSent] = useState(false); const [otp, setOtp] = useState('')
  const load = async (value = token) => { setBusy(true); setError(''); try { const data = await request(`/member?membership_token=${encodeURIComponent(value)}`); setDashboard(data); onToken(value); onProfile?.(data.member) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const passwordLogin = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const data = await request('/member/login/password', { method: 'POST', body: JSON.stringify({ email, password }) })
      onProfile?.(data.member)
      if (data.needs_plan) { onNeedsPlan?.(); return }
      setToken(data.membership_token); await load(data.membership_token)
    } catch (e) { setError(e.message); setBusy(false) }
  }
  useEffect(() => { if (initialToken) load(initialToken) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const switchMode = (next) => { setMode(next); setSent(false); setOtp(''); setError('') }
  const sendCode = async () => {
    setBusy(true); setError('')
    try {
      if (mode === 'email') await request('/member/login/email/start', { method: 'POST', body: JSON.stringify({ email }) })
      else await request('/member/login/start', { method: 'POST', body: JSON.stringify({ phone, channel }) })
      setSent(true)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const verifyCode = async () => {
    setBusy(true); setError('')
    try {
      const data = mode === 'email'
        ? await request('/member/login/email/verify', { method: 'POST', body: JSON.stringify({ email, code: otp }) })
        : await request('/member/login/verify', { method: 'POST', body: JSON.stringify({ phone, code: otp }) })
      setToken(data.membership_token); await load(data.membership_token)
    } catch (e) { setError(e.message); setBusy(false) }
  }
  const cancel = async (bookingId) => { if (!window.confirm('Cancel this class? Your credit will be restored.')) return; try { await request(`/bookings/${bookingId}/cancel`, { method: 'POST', body: JSON.stringify({ membership_token: token }) }); await load(); onChanged() } catch (e) { setError(e.message) } }
  return <Modal title="My ORTU bookings" onClose={onClose}>{!dashboard ? <div className="form">
    {mode === 'password' ? <form className="form" onSubmit={passwordLogin}>
      <label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" required /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
      {error && <p className="formError">{error}</p>}
      <button className="button wide" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button>
      {channels.email && <button type="button" className="linkButton" onClick={() => switchMode('email')}>Forgotten your password? Email me a sign-in code</button>}
      {channels.phone && <button type="button" className="linkButton" onClick={() => switchMode('phone')}>Log in with my mobile number instead</button>}
      <button type="button" className="linkButton" onClick={() => switchMode('code')}>Have a membership access code instead?</button>
    </form> : mode !== 'code' ? <>
      {mode === 'email'
        ? <label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" disabled={sent} /></label>
        : <label>Mobile number<input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+44 7700 900123" autoComplete="tel" disabled={sent} /></label>}
      {!sent ? <>
        {mode === 'phone' && <div className="channelPick"><span>Send my code by</span><button type="button" className={channel === 'whatsapp' ? 'active' : ''} onClick={() => setChannel('whatsapp')}>WhatsApp</button><button type="button" className={channel === 'sms' ? 'active' : ''} onClick={() => setChannel('sms')}>SMS</button></div>}
        {error && <p className="formError">{error}</p>}
        <button className="button wide" disabled={busy || (mode === 'email' ? !email.includes('@') : phone.trim().length < 7)} onClick={sendCode}>{busy ? 'Sending…' : mode === 'email' ? 'Email me a sign-in code' : `Send code by ${channel === 'whatsapp' ? 'WhatsApp' : 'SMS'}`}</button>
      </> : <>
        <label>Enter the 6-digit code we sent you<input inputMode="numeric" value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="123456" /></label>
        {error && <p className="formError">{error}</p>}
        <button className="button wide" disabled={busy || otp.trim().length < 4} onClick={verifyCode}>{busy ? 'Checking…' : 'Open my bookings'}</button>
        <button type="button" className="linkButton" onClick={() => { setSent(false); setOtp(''); setError('') }}>Change details or resend the code</button>
      </>}
      {channels.password && <button type="button" className="linkButton" onClick={() => switchMode('password')}>Log in with my password instead</button>}
      {mode === 'email' && channels.phone && <button type="button" className="linkButton" onClick={() => switchMode('phone')}>Log in with my mobile number instead</button>}
      {mode === 'phone' && channels.email && <button type="button" className="linkButton" onClick={() => switchMode('email')}>Log in with my email instead</button>}
      <button type="button" className="linkButton" onClick={() => switchMode('code')}>Have a membership access code instead?</button>
    </> : <>
      <label>Membership access code<input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste the code saved after joining" /></label>
      {error && <p className="formError">{error}</p>}
      <button className="button wide" disabled={busy || token.length < 20} onClick={() => load()}>{busy ? 'Loading…' : 'Open my membership'}</button>
      {channels.password && <button type="button" className="linkButton" onClick={() => switchMode('password')}>Log in with my password instead</button>}
      {(channels.email || channels.phone) && <button type="button" className="linkButton" onClick={() => switchMode(channels.email ? 'email' : 'phone')}>Log in with a one-time code instead</button>}
    </>}
  </div> : <div className="memberArea"><div className="memberHeader"><div><p>Welcome back</p><h3>{dashboard.member.first_name}</h3></div><div><span>{dashboard.membership.plan_name}</span><b>{dashboard.membership.remaining_classes == null ? 'Unlimited classes' : `${dashboard.membership.remaining_classes} credits left`}</b></div></div><h4>Upcoming bookings</h4>{dashboard.bookings.length ? dashboard.bookings.map((booking) => <article className="memberBooking" key={booking.booking_id}><div><b>{booking.session.name}</b><span>{formatDate(booking.session.start_at)}</span></div><button disabled={!booking.can_cancel} onClick={() => cancel(booking.booking_id)}>{booking.can_cancel ? 'Cancel booking' : 'Cancellation closed'}</button></article>) : <p className="emptySmall">No classes booked yet. Close this window and choose one from the timetable.</p>}{error && <p className="formError">{error}</p>}</div>}</Modal>
}

function SignupModal({ onClose }) {
  const [step, setStep] = useState(1)
  const [basic, setBasic] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const stepOne = (event) => {
    event.preventDefault()
    setBasic(Object.fromEntries(new FormData(event.currentTarget).entries()))
    setStep(2); setError('')
  }
  const submit = async (event) => {
    event.preventDefault(); setError('')
    const form = new FormData(event.currentTarget)
    if (form.get('password') !== form.get('confirm_password')) { setError('The two passwords do not match.'); return }
    setBusy(true)
    try {
      await request('/member/signup', { method: 'POST', body: JSON.stringify({
        first_name: basic.first_name, last_name: basic.last_name, date_of_birth: basic.date_of_birth,
        email: basic.email, phone: basic.phone || null, phone_other: basic.phone_other || null,
        address_house: basic.address_house || null, address_line1: basic.address_line1 || null, address_line2: basic.address_line2 || null,
        town: basic.town || null, county: basic.county || null, postcode: basic.postcode || null,
        kin_first_name: basic.kin_first_name, kin_last_name: basic.kin_last_name, kin_mobile: basic.kin_mobile,
        kin_email: basic.kin_email, kin_relationship: basic.kin_relationship || null, kin_is_primary_contact: basic.kin_is_primary_contact === 'on',
        contact2_name: basic.contact2_name || null, contact2_mobile: basic.contact2_mobile || null, contact2_email: basic.contact2_email || null, contact2_relationship: basic.contact2_relationship || null,
        health_notes: basic.health_notes || null, no_health_issues: basic.no_health_issues === 'on',
        password: form.get('password'), agree_terms: true, dp_legal: true, dp_services: true, dp_marketing: !!form.get('dp_marketing'),
      }) })
      setDone(true)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  if (done) return <Modal title="Request sent" onClose={onClose}><div className="form"><p>Your member record request has been sent to ORTU Fitness.</p><p className="adminMeta">The club reviews every request. You will receive an email as soon as you are accepted — then you can log in with your password, choose a membership plan and book classes.</p><button className="button wide" onClick={onClose}>Done</button></div></Modal>
  return <Modal title="Become a member" onClose={onClose} wide>
    <div className="stepDots"><span className={step === 1 ? 'active' : ''}>1</span><i /><span className={step === 2 ? 'active' : ''}>2</span></div>
    <p className="adminMeta stepIntro">{step === 1 ? 'Basic information — your member record will be created on the club system.' : 'Membership options — secure your account and confirm how ORTU may use your details.'}</p>
    {step === 1 ? <form className="form" onSubmit={stepOne}>
      <h4 className="formSection">Member information</h4>
      <div className="twoCols"><label>First name *<input name="first_name" required defaultValue={basic?.first_name} autoComplete="given-name" /></label><label>Last name *<input name="last_name" required defaultValue={basic?.last_name} autoComplete="family-name" /></label></div>
      <div className="twoCols"><label>Date of birth *<input name="date_of_birth" type="date" required defaultValue={basic?.date_of_birth} /></label><label>Email address *<input name="email" type="email" required defaultValue={basic?.email} autoComplete="email" /></label></div>
      <div className="twoCols"><label>Mobile<input name="phone" type="tel" defaultValue={basic?.phone} autoComplete="tel" /></label><label>Other number<input name="phone_other" type="tel" defaultValue={basic?.phone_other} /></label></div>
      <div className="twoCols"><label>House number or name<input name="address_house" defaultValue={basic?.address_house} /></label><label>Address line 1<input name="address_line1" defaultValue={basic?.address_line1} /></label></div>
      <div className="twoCols"><label>Address line 2<input name="address_line2" defaultValue={basic?.address_line2} /></label><label>Town or city<input name="town" defaultValue={basic?.town} /></label></div>
      <div className="twoCols"><label>County or area<input name="county" defaultValue={basic?.county} /></label><label>Postcode<input name="postcode" defaultValue={basic?.postcode} /></label></div>
      <h4 className="formSection">Next of kin / parent / guardian</h4>
      <div className="twoCols"><label>First name *<input name="kin_first_name" required defaultValue={basic?.kin_first_name} /></label><label>Last name *<input name="kin_last_name" required defaultValue={basic?.kin_last_name} /></label></div>
      <div className="twoCols"><label>Mobile *<input name="kin_mobile" type="tel" required defaultValue={basic?.kin_mobile} /></label><label>Email *<input name="kin_email" type="email" required defaultValue={basic?.kin_email} /></label></div>
      <label>Relationship to member<input name="kin_relationship" defaultValue={basic?.kin_relationship} placeholder="e.g. Parent, partner, friend" /></label>
      <label className="check"><input type="checkbox" name="kin_is_primary_contact" defaultChecked={basic?.kin_is_primary_contact === 'on'} /><span>This is the primary contact instead of the member.</span></label>
      <div className="twoCols"><label>Contact 2 name<input name="contact2_name" defaultValue={basic?.contact2_name} /></label><label>Contact 2 mobile<input name="contact2_mobile" type="tel" defaultValue={basic?.contact2_mobile} /></label></div>
      <div className="twoCols"><label>Contact 2 email<input name="contact2_email" type="email" defaultValue={basic?.contact2_email} /></label><label>Contact 2 relationship<input name="contact2_relationship" defaultValue={basic?.contact2_relationship} /></label></div>
      <h4 className="formSection">Medical information</h4>
      <label>Any injuries, allergies, disabilities, illnesses or relevant health concerns your instructors should know about?<textarea name="health_notes" rows="4" defaultValue={basic?.health_notes} placeholder="Add health notes…" /></label>
      <label className="check"><input type="checkbox" name="no_health_issues" defaultChecked={basic?.no_health_issues === 'on'} /><span>Tick if no health issues.</span></label>
      <button className="button wide">Next</button>
    </form> : <form className="form" onSubmit={submit}>
      <h4 className="formSection">Account password</h4>
      <p className="adminMeta">Create a password to log in and view or update your bookings. You will only be able to log in after the club has accepted your sign-up.</p>
      <div className="twoCols"><label>Password *<input name="password" type="password" required minLength="8" autoComplete="new-password" /></label><label>Confirm password *<input name="confirm_password" type="password" required minLength="8" autoComplete="new-password" /></label></div>
      <h4 className="formSection">Terms &amp; conditions</h4>
      <label className="check"><input type="checkbox" name="agree_terms" required /><span>I confirm that the information above is correct to the best of my knowledge and agree to ORTU Fitness storing it to manage my membership.</span></label>
      <h4 className="formSection">Data protection &amp; use</h4>
      <p className="adminMeta">Data protection best practice requires you to opt in for the club to use your data. The first two options are required.</p>
      <label className="check"><input type="checkbox" name="dp_legal" required /><span>I agree to ORTU Fitness using my data for legal reasons associated with the running of the club.</span></label>
      <label className="check"><input type="checkbox" name="dp_services" required /><span>I agree to ORTU Fitness using my data so that it can provide me with the club's services.</span></label>
      <label className="check"><input type="checkbox" name="dp_marketing" /><span>I agree to ORTU Fitness using my data so that I can receive benefits as part of my membership, including occasional marketing info.</span></label>
      {error && <p className="formError">{error}</p>}
      <div className="twoCols"><button type="button" className="button outline" onClick={() => setStep(1)}>Back</button><button className="button" disabled={busy}>{busy ? 'Sending…' : 'Submit request'}</button></div>
    </form>}
  </Modal>
}

const ADMIN_KEY_STORE = 'ortu_admin_key'
const MEMBERSHIP_STATUS = {
  active: ['Active', 'good'],
  pending_payment: ['Awaiting payment', 'warn'],
  payment_failed: ['Payment failed', 'bad'],
  suspended: ['Suspended', 'bad'],
}
const shortDate = (value) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
const money = (pence) => `£${(pence / 100).toFixed(2)}`

function AdminModal({ onClose, onChanged }) {
  const [key, setKey] = useState(() => sessionStorage.getItem(ADMIN_KEY_STORE) || '')
  const [authed, setAuthed] = useState(false)
  const [tab, setTab] = useState('classes')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sessions, setSessions] = useState([])
  const [members, setMembers] = useState(null)

  const adminRequest = (path, options = {}) => request(path, { ...options, headers: { 'X-Ortu-Admin-Key': key, ...(options.headers || {}) } })
  const loadSessions = () => adminRequest('/admin/sessions').then(setSessions)
  const loadMembers = () => adminRequest('/admin/members').then(setMembers)

  const unlock = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await loadSessions(); sessionStorage.setItem(ADMIN_KEY_STORE, key); setAuthed(true) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  useEffect(() => {
    if (key) loadSessions().then(() => setAuthed(true)).catch(() => sessionStorage.removeItem(ADMIN_KEY_STORE))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (authed && tab === 'members' && !members) loadMembers().catch((e) => setError(e.message))
  }, [authed, tab]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!authed) return <Modal title="Studio login" onClose={onClose}>
    <form className="form" onSubmit={unlock}>
      <label>Studio admin key<input type="password" required value={key} onChange={(e) => setKey(e.target.value)} /></label>
      {error && <p className="formError">{error}</p>}
      <button className="button wide" disabled={busy || !key}>{busy ? 'Checking…' : 'Open studio dashboard'}</button>
    </form>
  </Modal>

  return <Modal title="Studio dashboard" onClose={onClose} wide>
    <div className="adminTabs">
      <button className={tab === 'classes' ? 'active' : ''} onClick={() => setTab('classes')}>Timetable</button>
      <button className={tab === 'members' ? 'active' : ''} onClick={() => setTab('members')}>Members</button>
    </div>
    {error && <p className="formError">{error}</p>}
    {tab === 'classes' && <AdminClasses sessions={sessions} adminRequest={adminRequest} refresh={() => { loadSessions().catch((e) => setError(e.message)); onChanged() }} />}
    {tab === 'members' && <AdminMembers data={members} adminRequest={adminRequest} refresh={() => loadMembers().catch((e) => setError(e.message))} />}
  </Modal>
}

function AdminClasses({ sessions, adminRequest, refresh }) {
  const [showCreate, setShowCreate] = useState(false)
  const [openId, setOpenId] = useState(null)
  const [register, setRegister] = useState(null)
  const [capacity, setCapacity] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const openRegister = async (session) => {
    if (openId === session.id) { setOpenId(null); setRegister(null); return }
    setOpenId(session.id); setRegister(null); setCapacity(String(session.capacity)); setError('')
    try { setRegister(await adminRequest(`/admin/sessions/${session.id}/bookings`)) } catch (e) { setError(e.message) }
  }
  const patch = async (sessionId, payload, message) => {
    setError(''); setSuccess('')
    try {
      await adminRequest(`/admin/sessions/${sessionId}`, { method: 'PATCH', body: JSON.stringify(payload) })
      setSuccess(message); refresh()
      if (openId === sessionId) setRegister(await adminRequest(`/admin/sessions/${sessionId}/bookings`))
    } catch (e) { setError(e.message) }
  }
  return <div>
    <button className="button small" onClick={() => setShowCreate(!showCreate)}>{showCreate ? 'Hide new class form' : '＋ Publish a new class'}</button>
    {showCreate && <AdminCreateClass adminRequest={adminRequest} onCreated={() => { setShowCreate(false); setSuccess('Class published to the live timetable.'); refresh() }} />}
    {error && <p className="formError">{error}</p>}{success && <p className="formSuccess">{success}</p>}
    <div className="adminList">
      {sessions.map((session) => {
        const past = new Date(session.start_at) < new Date()
        return <div key={session.id}>
          <div className="adminRow">
            <div>
              <b>{session.name}<span className={`statusTag ${session.status === 'cancelled' ? 'bad' : past ? '' : 'good'}`}>{session.status === 'cancelled' ? 'Cancelled' : past ? 'Past' : 'Scheduled'}</span></b>
              <p className="adminMeta">{formatDate(session.start_at)} · {session.coach_name} · {session.booked}/{session.capacity} booked</p>
            </div>
            <div className="adminActions">
              <button onClick={() => openRegister(session)}>{openId === session.id ? 'Close register' : 'Register'}</button>
              {!past && (session.status === 'cancelled'
                ? <button onClick={() => patch(session.id, { status: 'scheduled' }, 'Class restored to the timetable.')}>Restore</button>
                : <button onClick={() => patch(session.id, { status: 'cancelled' }, 'Class cancelled.')}>Cancel class</button>)}
            </div>
          </div>
          {openId === session.id && <div className="adminPanel">
            <div className="capacityEdit"><b>Capacity</b><input type="number" min="1" max="500" value={capacity} onChange={(e) => setCapacity(e.target.value)} /><button className="button small" onClick={() => patch(session.id, { capacity: Number(capacity) }, 'Capacity updated.')}>Save</button></div>
            {!register ? <p className="adminMeta">Loading register…</p> : register.bookings.length ? register.bookings.map((booking) => <div className="registerRow" key={booking.booking_id}>
              <div><b>{booking.member.first_name} {booking.member.last_name}</b><span className="adminMeta"> · {booking.plan_name}</span>{booking.status !== 'confirmed' && <span className="statusTag bad">Cancelled</span>}</div>
              <p className="adminMeta">{booking.member.email}{booking.member.phone ? ` · ${booking.member.phone}` : ''} · booked {shortDate(booking.booked_at)}</p>
            </div>) : <p className="adminMeta">No bookings for this class yet.</p>}
          </div>}
        </div>
      })}
      {!sessions.length && <p className="emptySmall">No classes yet — publish your first one above.</p>}
    </div>
  </div>
}

function AdminCreateClass({ adminRequest, onCreated }) {
  const [error, setError] = useState('')
  const submit = async (event) => {
    event.preventDefault(); setError('')
    const form = new FormData(event.currentTarget)
    try {
      await adminRequest('/admin/sessions', { method: 'POST', body: JSON.stringify({ name: form.get('name'), coach_name: form.get('coach_name'), location: form.get('location'), description: form.get('description'), start_at: new Date(form.get('start_at')).toISOString(), end_at: new Date(form.get('end_at')).toISOString(), capacity: Number(form.get('capacity')) }) })
      onCreated()
    } catch (e) { setError(e.message) }
  }
  return <form className="form adminCreate" onSubmit={submit}>
    <label>Class name<input name="name" required placeholder="Strength & Conditioning" /></label>
    <div className="twoCols"><label>Coach<input name="coach_name" placeholder="Coach name" /></label><label>Capacity<input name="capacity" required type="number" min="1" max="500" defaultValue="12" /></label></div>
    <label>Location<input name="location" placeholder="ORTU Fitness Studio" /></label>
    <div className="twoCols"><label>Starts<input name="start_at" required type="datetime-local" /></label><label>Ends<input name="end_at" required type="datetime-local" /></label></div>
    <label>Description<textarea name="description" rows="3" placeholder="What members can expect" /></label>
    {error && <p className="formError">{error}</p>}
    <button className="button wide">Publish class</button>
  </form>
}

function MemberDetails({ m }) {
  return <div className="adminPanel memberDetails">
    <p className="adminMeta">{m.date_of_birth ? `Date of birth ${shortDate(m.date_of_birth)} · ` : ''}{m.phone_other ? `Other number ${m.phone_other} · ` : ''}{m.address || 'No address given'}</p>
    <p className="adminMeta"><b>Next of kin:</b> {m.kin?.name ? `${m.kin.name}${m.kin.relationship ? ` (${m.kin.relationship})` : ''} · ${[m.kin.mobile, m.kin.email].filter(Boolean).join(' · ')}${m.kin.is_primary_contact ? ' · primary contact' : ''}` : 'not given'}</p>
    {m.contact2?.name && <p className="adminMeta"><b>Contact 2:</b> {m.contact2.name}{m.contact2.relationship ? ` (${m.contact2.relationship})` : ''} · {[m.contact2.mobile, m.contact2.email].filter(Boolean).join(' · ')}</p>}
    <p className="adminMeta"><b>Medical:</b> {m.no_health_issues ? 'No health issues declared' : (m.health_notes || 'Not provided')}</p>
  </div>
}

function AdminMembers({ data, adminRequest, refresh }) {
  const [openId, setOpenId] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  if (!data) return <p className="adminMeta">Loading members…</p>
  const base = data.gocardless_dashboard_url
  const pending = data.members.filter((m) => m.approval_status === 'pending')
  const rest = data.members.filter((m) => m.approval_status !== 'pending')
  const decide = async (member, action) => {
    setError(''); setNotice('')
    try {
      const result = await adminRequest(`/admin/members/${member.id}/approval`, { method: 'POST', body: JSON.stringify({ action }) })
      const mail = result.notification_email === 'sent' ? ' Notification email sent.' : result.notification_email === 'failed' ? ' The notification email could not be sent.' : ''
      setNotice(`${member.first_name} ${member.last_name} ${action === 'approve' ? 'approved.' : 'declined.'}${mail}`)
      refresh()
    } catch (e) { setError(e.message) }
  }
  return <div>
    {error && <p className="formError">{error}</p>}{notice && <p className="formSuccess">{notice}</p>}
    {pending.length > 0 && <>
      <h4 className="formSection">Member record requests ({pending.length})</h4>
      {pending.map((member) => <div className="adminMemberCard" key={member.id}>
        <div><b>{member.first_name} {member.last_name}</b><span className="statusTag warn">Awaiting approval</span></div>
        <p className="adminMeta">{member.email}{member.phone ? ` · ${member.phone}` : ''} · requested {shortDate(member.joined_at)}</p>
        <MemberDetails m={member} />
        <div className="adminActions"><button onClick={() => decide(member, 'approve')}>Approve</button><button onClick={() => decide(member, 'decline')}>Decline</button></div>
      </div>)}
    </>}
    <div className="adminToolbar">
      <p className="adminMeta">{rest.length} member{rest.length === 1 ? '' : 's'} · payment records open in the GoCardless dashboard</p>
      <button className="button small" onClick={refresh}>Refresh</button>
    </div>
    {rest.length ? rest.map((member) => <div className="adminMemberCard" key={member.id}>
      <div><b>{member.first_name} {member.last_name}</b>{member.approval_status === 'declined' && <span className="statusTag bad">Declined</span>}{member.marketing_opt_in && <span className="statusTag good">Marketing OK</span>}</div>
      <p className="adminMeta">{member.email}{member.phone ? ` · ${member.phone}` : ''} · joined {shortDate(member.joined_at)} · {member.confirmed_bookings} booking{member.confirmed_bookings === 1 ? '' : 's'}</p>
      <button type="button" className="linkButton" onClick={() => setOpenId(openId === member.id ? null : member.id)}>{openId === member.id ? 'Hide record details' : 'Show record details'}</button>
      {openId === member.id && <MemberDetails m={member} />}
      {member.memberships.map((membership) => {
        const [label, tone] = MEMBERSHIP_STATUS[membership.status] || [membership.status, '']
        return <div className="membershipLine" key={membership.id}>
          <span className={`statusTag ${tone}`}>{label}</span>
          <b>{membership.plan_name}</b>
          <span className="adminMeta">{money(membership.amount_pence)}{membership.billing_kind === 'recurring' ? '/month' : ''}{membership.remaining_classes != null ? ` · ${membership.remaining_classes} credits left` : ' · unlimited'}{membership.ends_at ? ` · until ${shortDate(membership.ends_at)}` : ''}</span>
          <span className="gcLinks">
            {membership.gocardless_mandate_id && <a href={`${base}/mandates/${membership.gocardless_mandate_id}`} target="_blank" rel="noreferrer">Mandate</a>}
            {membership.gocardless_subscription_id && <a href={`${base}/subscriptions/${membership.gocardless_subscription_id}`} target="_blank" rel="noreferrer">Subscription</a>}
            {membership.gocardless_payment_id && <a href={`${base}/payments/${membership.gocardless_payment_id}`} target="_blank" rel="noreferrer">Payment</a>}
          </span>
        </div>
      })}
      {!member.memberships.length && <p className="adminMeta">No membership records yet — approved but no plan purchased.</p>}
    </div>) : <p className="emptySmall">No members yet. They appear here as soon as a member record request arrives.</p>}
  </div>
}

export default App
