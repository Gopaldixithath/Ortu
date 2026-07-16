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

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const close = (event) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [onClose])
  return <div className="modalBackdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
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
  const [membershipToken, setMembershipToken] = useState(() => localStorage.getItem(MEMBERSHIP_KEY) || '')

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
      <div className="headerActions"><button className="textButton" onClick={() => setShowMember(true)}>My bookings</button><a className="button small" href="#classes">Book a class</a></div>
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
          <button className={plan.featured ? 'button' : 'button outline'} onClick={() => setJoinPlan(plan)}>Choose plan</button>
        </article>)}</div>
        {!site.payments_ready && <div className="setupBanner"><b>Payments are in setup mode.</b> Add the GoCardless environment settings before accepting live memberships.</div>}
      </section>

      <section className="section values" id="about">
        <div className="valuesLead"><p className="eyebrow">WHY ORTU</p><h2>Good training<br />changes more<br />than your body.</h2><p>ORTU is designed for real people: expert direction, encouraging energy and enough variety to keep you moving forward.</p></div>
        <div className="valueCards"><article><span>01</span><h3>Coaching that sees you</h3><p>Every movement can be scaled. Come as you are and leave feeling capable.</p></article><article><span>02</span><h3>Small groups, real attention</h3><p>Class capacities protect the quality, safety and energy of every session.</p></article><article><span>03</span><h3>Consistency without pressure</h3><p>Choose one session or unlimited access. Your routine can grow with you.</p></article></div>
      </section>

      <section className="cta"><p className="eyebrow light">READY WHEN YOU ARE</p><h2>Your strongest chapter<br />can start today.</h2><a className="button" href="#memberships">Choose your membership <span>↗</span></a></section>
    </main>

    <footer><div><Mark /><p>Small-group health and fitness with room for everyone to progress.</p></div><div><b>EXPLORE</b><a href="#classes">Classes</a><a href="#memberships">Memberships</a><a href="#about">Why ORTU</a></div><div><b>MEMBERS</b><button onClick={() => setShowMember(true)}>My bookings</button><button onClick={() => setShowAdmin(true)}>Studio login</button></div><div><b>PAYMENTS</b><p>Securely processed by GoCardless</p><p>Cancellation cutoff: 1 hour</p></div></footer>

    {joinPlan && <JoinModal plan={joinPlan} paymentsReady={site.payments_ready} onClose={() => setJoinPlan(null)} setNotice={setNotice} />}
    {bookingSession && <BookingModal session={bookingSession} membershipToken={membershipToken} onClose={() => setBookingSession(null)} onBooked={() => { setBookingSession(null); loadSite(); setNotice('Class booked — we look forward to seeing you.'); setShowMember(true) }} />}
    {showMember && <MemberModal initialToken={membershipToken} onToken={(token) => { setMembershipToken(token); localStorage.setItem(MEMBERSHIP_KEY, token) }} onClose={() => setShowMember(false)} onChanged={loadSite} />}
    {showAdmin && <AdminModal onClose={() => setShowAdmin(false)} onChanged={loadSite} />}
  </div>
}

function JoinModal({ plan, paymentsReady, onClose, setNotice }) {
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
  return <Modal title={`Join with ${plan.name}`} onClose={onClose}><div className="checkoutSummary"><span>{plan.description}</span><b>{plan.price}{plan.billing_kind === 'recurring' ? ' monthly' : ''}</b></div><form className="form" onSubmit={submit}><div className="twoCols"><label>First name<input required name="first_name" autoComplete="given-name" /></label><label>Last name<input required name="last_name" autoComplete="family-name" /></label></div><label>Email address<input required type="email" name="email" autoComplete="email" /></label><label>Mobile number <small>optional</small><input name="phone" type="tel" autoComplete="tel" /></label><label className="check"><input type="checkbox" name="marketing_opt_in" /><span>Send me useful ORTU updates and offers.</span></label>{error && <p className="formError">{error}</p>}<button className="button wide" disabled={busy || !paymentsReady}>{busy ? 'Opening secure payment…' : paymentsReady ? 'Continue to GoCardless' : 'Payments not yet connected'}</button><p className="fineprint">Your bank details are entered on GoCardless’s secure hosted payment page. ORTU does not store them.</p></form></Modal>
}

function BookingModal({ session, membershipToken, onClose, onBooked }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const confirm = async () => { setBusy(true); setError(''); try { await request('/bookings', { method: 'POST', body: JSON.stringify({ membership_token: membershipToken, session_id: session.id }) }); onBooked() } catch (e) { setError(e.message); setBusy(false) } }
  return <Modal title="Confirm your class" onClose={onClose}><div className="bookingConfirm"><span className="pill">{session.coach_name}</span><h3>{session.name}</h3><p>{formatDate(session.start_at)}</p><p>{session.location}</p><div className="bookingRule"><b>{session.remaining} spaces currently available</b><span>Bookings are confirmed live and cannot exceed the class capacity.</span></div>{error && <p className="formError">{error}</p>}<button className="button wide" disabled={busy} onClick={confirm}>{busy ? 'Securing your space…' : 'Confirm booking'}</button></div></Modal>
}

function MemberModal({ initialToken, onToken, onClose, onChanged }) {
  const [token, setToken] = useState(initialToken); const [dashboard, setDashboard] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const load = async (value = token) => { setBusy(true); setError(''); try { const data = await request(`/member?membership_token=${encodeURIComponent(value)}`); setDashboard(data); onToken(value) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { if (initialToken) load(initialToken) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const cancel = async (bookingId) => { if (!window.confirm('Cancel this class? Your credit will be restored.')) return; try { await request(`/bookings/${bookingId}/cancel`, { method: 'POST', body: JSON.stringify({ membership_token: token }) }); await load(); onChanged() } catch (e) { setError(e.message) } }
  return <Modal title="My ORTU bookings" onClose={onClose}>{!dashboard ? <div className="form"><label>Membership access code<input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste the code saved after joining" /></label>{error && <p className="formError">{error}</p>}<button className="button wide" disabled={busy || token.length < 20} onClick={() => load()}>{busy ? 'Loading…' : 'Open my membership'}</button></div> : <div className="memberArea"><div className="memberHeader"><div><p>Welcome back</p><h3>{dashboard.member.first_name}</h3></div><div><span>{dashboard.membership.plan_name}</span><b>{dashboard.membership.remaining_classes == null ? 'Unlimited classes' : `${dashboard.membership.remaining_classes} credits left`}</b></div></div><h4>Upcoming bookings</h4>{dashboard.bookings.length ? dashboard.bookings.map((booking) => <article className="memberBooking" key={booking.booking_id}><div><b>{booking.session.name}</b><span>{formatDate(booking.session.start_at)}</span></div><button disabled={!booking.can_cancel} onClick={() => cancel(booking.booking_id)}>{booking.can_cancel ? 'Cancel booking' : 'Cancellation closed'}</button></article>) : <p className="emptySmall">No classes booked yet. Close this window and choose one from the timetable.</p>}{error && <p className="formError">{error}</p>}</div>}</Modal>
}

function AdminModal({ onClose, onChanged }) {
  const [key, setKey] = useState(''); const [error, setError] = useState(''); const [success, setSuccess] = useState('')
  const submit = async (event) => { event.preventDefault(); setError(''); setSuccess(''); const form = new FormData(event.currentTarget); try { await request('/admin/sessions', { method: 'POST', headers: { 'X-Ortu-Admin-Key': key }, body: JSON.stringify({ name: form.get('name'), coach_name: form.get('coach_name'), location: form.get('location'), description: form.get('description'), start_at: new Date(form.get('start_at')).toISOString(), end_at: new Date(form.get('end_at')).toISOString(), capacity: Number(form.get('capacity')) }) }); setSuccess('Class published to the live timetable.'); event.currentTarget.reset(); onChanged() } catch (e) { setError(e.message) } }
  return <Modal title="Studio timetable setup" onClose={onClose}><form className="form" onSubmit={submit}><label>Studio admin key<input type="password" required value={key} onChange={(e) => setKey(e.target.value)} /></label><label>Class name<input name="name" required placeholder="Strength & Conditioning" /></label><div className="twoCols"><label>Coach<input name="coach_name" placeholder="Coach name" /></label><label>Capacity<input name="capacity" required type="number" min="1" max="500" defaultValue="12" /></label></div><label>Location<input name="location" placeholder="ORTU Fitness Studio" /></label><div className="twoCols"><label>Starts<input name="start_at" required type="datetime-local" /></label><label>Ends<input name="end_at" required type="datetime-local" /></label></div><label>Description<textarea name="description" rows="3" placeholder="What members can expect" /></label>{error && <p className="formError">{error}</p>}{success && <p className="formSuccess">{success}</p>}<button className="button wide">Publish class</button></form></Modal>
}

export default App
